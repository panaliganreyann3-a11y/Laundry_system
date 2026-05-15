from django.core import mail
from django.test import TestCase, Client, override_settings
from django.contrib.auth.models import User, Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone

from .models import ActivityLog, Customer, Order, Payment, PricingConfig, RewardTransaction
from .validators import is_gmail_email
from .views import expire_customer_points, redeem_points_for_order


def make_admin(username='admin', password='adminpass123'):
    user = User.objects.create_user(username=username, password=password)
    user.is_superuser = True
    user.is_staff = True
    user.save()
    return user


def make_staff(username='staff', password='staffpass123'):
    user = User.objects.create_user(username=username, password=password)
    group, _ = Group.objects.get_or_create(name='Staff')
    user.groups.add(group)
    return user


def make_customer(name='Test Customer', contact='09123456789'):
    return Customer.objects.create(name=name, contact=contact)


def make_config(price_per_kg=30.0, rush_surcharge=50.0):
    return PricingConfig.objects.create(price_per_kg=price_per_kg, rush_surcharge=rush_surcharge)


class PriceCalculationTest(TestCase):
    def test_standard_order_price(self):
        config = make_config(price_per_kg=30.0, rush_surcharge=50.0)
        price = round(5.0 * config.price_per_kg, 2)
        self.assertEqual(price, 150.0)

    def test_rush_order_price(self):
        config = make_config(price_per_kg=30.0, rush_surcharge=50.0)
        price = round(5.0 * config.price_per_kg + config.rush_surcharge, 2)
        self.assertEqual(price, 200.0)

    def test_price_via_add_order_view(self):
        admin = make_admin()
        customer = make_customer()
        make_config(price_per_kg=30.0, rush_surcharge=50.0)
        self.client.force_login(admin)
        self.client.post(reverse('add_order'), {
            'customer': customer.id,
            'weight': '5',
            'service_type': 'WASH_DRY_FOLD',
            'payment_status': 'UNPAID',
        })
        order = Order.objects.first()
        self.assertIsNotNone(order)
        self.assertEqual(order.price, 150.0)

    def test_rush_price_via_add_order_view(self):
        admin = make_admin()
        customer = make_customer()
        make_config(price_per_kg=30.0, rush_surcharge=50.0)
        self.client.force_login(admin)
        self.client.post(reverse('add_order'), {
            'customer': customer.id,
            'weight': '5',
            'service_type': 'WASH_DRY_FOLD',
            'priority': 'on',
            'payment_status': 'UNPAID',
        })
        order = Order.objects.first()
        self.assertEqual(order.price, 200.0)
        self.assertTrue(order.is_priority)


class StatusWorkflowTest(TestCase):
    def setUp(self):
        self.customer = make_customer()
        self.order = Order.objects.create(
            customer=self.customer,
            weight=3.0,
            price=90.0,
            service_type='WASH_DRY',
        )

    def test_initial_status_is_received(self):
        self.assertEqual(self.order.status, 'RECEIVED_AT_SHOP')

    def test_next_status_flow(self):
        flow = ['WEIGHED', 'PROCESSING', 'READY_FOR_PICKUP']
        for expected in flow:
            self.assertEqual(self.order.get_next_status(), expected)
            self.order.status = expected
            self.order.save()
        self.order.payment_status = 'PAID'
        self.assertEqual(self.order.get_next_status(), 'COMPLETED')

    def test_no_next_status_after_completed(self):
        self.order.status = 'COMPLETED'
        self.order.save()
        self.assertIsNone(self.order.get_next_status())

    def test_is_complete(self):
        self.assertFalse(self.order.is_complete())
        self.order.status = 'COMPLETED'
        self.assertTrue(self.order.is_complete())

    def test_update_status_view_advances_order(self):
        admin = make_admin()
        self.client.force_login(admin)
        self.client.get(reverse('update_status', args=[self.order.id]))
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'WEIGHED')

    def test_update_status_sets_completed_at_alias(self):
        admin = make_admin()
        self.client.force_login(admin)
        self.order.status = 'READY_FOR_PICKUP'
        self.order.payment_status = 'PAID'
        self.order.save()
        self.client.get(reverse('update_status', args=[self.order.id]))
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, 'COMPLETED')
        self.assertIsNotNone(self.order.claimed_at)

    def test_verified_gcash_payment_allows_processing(self):
        staff = make_staff()
        self.client.force_login(staff)
        self.order.status = 'BILL_SENT'
        self.order.payment_method = 'GCASH'
        self.order.total_amount = 90
        self.order.balance = 90
        self.order.payment_status = 'PENDING_VERIFICATION'
        self.order.save()
        Payment.objects.create(
            order=self.order,
            payment_method='GCASH',
            amount=90,
            status='VERIFIED',
            reference_number='GCASH123',
        )

        self.client.get(reverse('update_status', args=[self.order.id]))
        self.order.refresh_from_db()

        self.assertEqual(self.order.payment_status, 'PAID')
        self.assertEqual(self.order.status, 'PROCESSING')

    def test_customer_gcash_payment_must_cover_balance(self):
        user = User.objects.create_user(
            username='customer@example.com',
            email='customer@example.com',
            password='customerpass123',
        )
        customer = Customer.objects.create(
            user=user,
            name='GCash Customer',
            contact='09999999999',
            email='customer@example.com',
            address='Test address',
        )
        order = Order.objects.create(
            customer=customer,
            status='BILL_SENT',
            payment_method='GCASH',
            total_amount=150,
            balance=150,
            payment_status='UNPAID',
        )
        self.client.force_login(user)

        self.client.post(reverse('submit_gcash_payment', args=[order.id]), {
            'amount': '100',
            'reference_number': 'UNDERPAID',
            'proof_image': SimpleUploadedFile('proof.jpg', b'proof', content_type='image/jpeg'),
        })

        self.assertFalse(Payment.objects.filter(order=order).exists())

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_walkin_ready_for_pickup_sends_customer_email(self):
        self.customer.email = 'walkin.customer@gmail.com'
        self.customer.save(update_fields=['email'])
        self.order.status = 'PROCESSING'
        self.order.save(update_fields=['status'])
        staff = make_staff()
        self.client.force_login(staff)

        self.client.get(reverse('update_status', args=[self.order.id]))

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('ready for pickup', mail.outbox[0].subject.lower())
        self.assertEqual(mail.outbox[0].to, ['walkin.customer@gmail.com'])

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_pickup_delivery_out_for_delivery_sends_customer_email(self):
        customer = Customer.objects.create(
            name='Delivery Customer',
            contact='09111111112',
            email='delivery.customer@gmail.com',
        )
        order = Order.objects.create(
            customer=customer,
            order_type='PICKUP_DELIVERY',
            status='READY_FOR_DELIVERY',
            payment_method='CASH_AFTER_DELIVERY',
        )
        staff = make_staff()
        self.client.force_login(staff)

        self.client.get(reverse('update_status', args=[order.id]))

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('out for delivery', mail.outbox[0].subject.lower())
        self.assertEqual(mail.outbox[0].to, ['delivery.customer@gmail.com'])

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_processing_sends_customer_email(self):
        self.customer.email = 'processing.customer@gmail.com'
        self.customer.save(update_fields=['email'])
        self.order.status = 'WEIGHED'
        self.order.save(update_fields=['status'])
        staff = make_staff()
        self.client.force_login(staff)

        self.client.get(reverse('update_status', args=[self.order.id]))

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('being processed', mail.outbox[0].subject.lower())
        self.assertEqual(mail.outbox[0].to, ['processing.customer@gmail.com'])

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_pickup_accepted_sends_customer_email(self):
        customer = Customer.objects.create(
            name='Pickup Customer',
            contact='09111111113',
            email='pickup.customer@gmail.com',
        )
        order = Order.objects.create(
            customer=customer,
            order_type='PICKUP_DELIVERY',
            status='PENDING_PICKUP',
        )
        staff = make_staff()
        self.client.force_login(staff)

        self.client.post(reverse('accept_pickup_request', args=[order.id]))

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('going to pick up', mail.outbox[0].subject.lower())
        self.assertEqual(mail.outbox[0].to, ['pickup.customer@gmail.com'])

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_pickup_delivery_ready_for_delivery_sends_customer_email(self):
        customer = Customer.objects.create(
            name='Ready Delivery Customer',
            contact='09111111114',
            email='ready.delivery.customer@gmail.com',
        )
        order = Order.objects.create(
            customer=customer,
            order_type='PICKUP_DELIVERY',
            status='PROCESSING',
        )
        staff = make_staff()
        self.client.force_login(staff)

        self.client.get(reverse('update_status', args=[order.id]))

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('done processing', mail.outbox[0].subject.lower())
        self.assertEqual(mail.outbox[0].to, ['ready.delivery.customer@gmail.com'])


class CustomerAccountEmailValidationTest(TestCase):
    def test_customer_account_requires_gmail(self):
        self.assertTrue(is_gmail_email('customer@gmail.com'))
        self.assertFalse(is_gmail_email('customer@yahoo.com'))


class RewardsFlowTest(TestCase):
    def setUp(self):
        self.staff = make_staff()
        self.customer = make_customer()
        make_config()

    def test_completed_paid_order_awards_points_once(self):
        order = Order.objects.create(
            customer=self.customer,
            status='READY_FOR_PICKUP',
            payment_status='PAID',
            total_amount=100,
            amount_paid=100,
        )
        self.client.force_login(self.staff)

        self.client.get(reverse('update_status', args=[order.id]))
        self.client.get(reverse('update_status', args=[order.id]))

        self.customer.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(order.status, 'COMPLETED')
        self.assertTrue(order.points_awarded)
        self.assertEqual(self.customer.loyalty_points, 1)
        self.assertEqual(RewardTransaction.objects.filter(transaction_type=RewardTransaction.EARN).count(), 1)

    def test_unpaid_order_does_not_award_points(self):
        order = Order.objects.create(
            customer=self.customer,
            status='READY_FOR_PICKUP',
            payment_status='UNPAID',
            total_amount=100,
        )
        self.client.force_login(self.staff)

        self.client.get(reverse('update_status', args=[order.id]))

        self.customer.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(order.status, 'READY_FOR_PICKUP')
        self.assertFalse(order.points_awarded)
        self.assertEqual(self.customer.loyalty_points, 0)

    def test_redeem_points_adds_discount_and_balances_points(self):
        self.customer.loyalty_points = 20
        self.customer.points_last_transaction_at = timezone.now()
        self.customer.save(update_fields=['loyalty_points', 'points_last_transaction_at'])
        order = Order.objects.create(
            customer=self.customer,
            status='WEIGHED',
            weight=5,
            price_per_kg=30,
            payment_status='UNPAID',
        )
        order.calculate_totals()
        order.save()

        ok, _message = redeem_points_for_order(order, 10)

        self.assertTrue(ok)
        self.customer.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(self.customer.loyalty_points, 10)
        self.assertEqual(order.points_redeemed, 10)
        self.assertEqual(order.points_discount, 50)
        self.assertEqual(order.total_amount, 100)

    def test_cancelled_order_cannot_redeem_points(self):
        self.customer.loyalty_points = 10
        self.customer.points_last_transaction_at = timezone.now()
        self.customer.save(update_fields=['loyalty_points', 'points_last_transaction_at'])
        order = Order.objects.create(customer=self.customer, status='CANCELLED', payment_status='CANCELLED')

        ok, _message = redeem_points_for_order(order, 10)

        self.customer.refresh_from_db()
        self.assertFalse(ok)
        self.assertEqual(self.customer.loyalty_points, 10)

    def test_points_expire_after_six_months_without_transaction(self):
        self.customer.loyalty_points = 10
        self.customer.points_last_transaction_at = timezone.now() - timezone.timedelta(days=184)
        self.customer.save(update_fields=['loyalty_points', 'points_last_transaction_at'])

        expired = expire_customer_points(self.customer)

        self.customer.refresh_from_db()
        self.assertEqual(expired, 10)
        self.assertEqual(self.customer.loyalty_points, 0)
        self.assertEqual(RewardTransaction.objects.filter(transaction_type=RewardTransaction.EXPIRE).count(), 1)


class RoleBasedAccessTest(TestCase):
    def setUp(self):
        self.admin = make_admin()
        self.staff = make_staff()
        make_config()

    def test_admin_can_access_reports(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('reports'))
        self.assertEqual(response.status_code, 200)

    def test_admin_can_access_activity_log(self):
        ActivityLog.objects.create(
            actor=self.admin,
            category='ACCOUNT',
            action='CREATE',
            description='Created a test account.',
        )
        self.client.force_login(self.admin)
        response = self.client.get(reverse('activity_log'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Created a test account.')

    def test_staff_cannot_access_activity_log(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse('activity_log'))
        self.assertEqual(response.status_code, 403)

    def test_admin_nav_includes_activity_log(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('admin_dashboard'))
        self.assertContains(response, reverse('activity_log'))

    def test_staff_cannot_access_reports(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse('reports'))
        self.assertEqual(response.status_code, 403)

    def test_admin_can_access_pricing(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('pricing_settings'))
        self.assertEqual(response.status_code, 200)

    def test_staff_cannot_access_pricing(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse('pricing_settings'))
        self.assertEqual(response.status_code, 403)

    def test_unauthenticated_redirected_to_login(self):
        response = self.client.get(reverse('admin_dashboard'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/login/', response['Location'])

    def test_single_login_redirects_admin_to_admin_dashboard(self):
        response = self.client.post(reverse('login'), {
            'username': self.admin.username,
            'password': 'adminpass123',
        })
        self.assertRedirects(response, reverse('admin_dashboard'))

    def test_single_login_redirects_staff_to_staff_dashboard(self):
        response = self.client.post(reverse('login'), {
            'username': self.staff.username,
            'password': 'staffpass123',
        })
        self.assertRedirects(response, reverse('staff_dashboard'))

    def test_single_login_redirects_customer_to_customer_dashboard(self):
        user = User.objects.create_user(
            username='customer@example.com',
            email='customer@example.com',
            password='customerpass123',
        )
        Customer.objects.create(
            user=user,
            name='Portal Customer',
            contact='09111111111',
            email='customer@example.com',
            address='Test address',
        )
        response = self.client.post(reverse('login'), {
            'username': 'customer@example.com',
            'password': 'customerpass123',
        })
        self.assertRedirects(response, reverse('customer_dashboard'))

    def test_admin_dashboard_redirects_staff(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse('admin_dashboard'))
        self.assertRedirects(response, reverse('staff_dashboard'))

    def test_staff_dashboard_redirects_admin(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('staff_dashboard'))
        self.assertRedirects(response, reverse('admin_dashboard'))


class WeightValidationTest(TestCase):
    def setUp(self):
        self.admin = make_admin()
        self.customer = make_customer()
        make_config()
        self.client.force_login(self.admin)

    def test_zero_weight_rejected(self):
        self.client.post(reverse('add_order'), {
            'customer': self.customer.id,
            'weight': '0',
            'service_type': 'WASH',
            'payment_status': 'UNPAID',
        })
        self.assertEqual(Order.objects.count(), 0)

    def test_negative_weight_rejected(self):
        self.client.post(reverse('add_order'), {
            'customer': self.customer.id,
            'weight': '-3',
            'service_type': 'WASH',
            'payment_status': 'UNPAID',
        })
        self.assertEqual(Order.objects.count(), 0)


class QueueNumberTest(TestCase):
    def test_queue_number_increments_daily(self):
        admin = make_admin()
        customer = make_customer()
        make_config()
        self.client.force_login(admin)

        for _ in range(3):
            self.client.post(reverse('add_order'), {
                'customer': customer.id,
                'weight': '2',
                'service_type': 'WASH',
                'payment_status': 'UNPAID',
            })

        queue_numbers = list(Order.objects.order_by('queue_number').values_list('queue_number', flat=True))
        self.assertEqual(queue_numbers, [1, 2, 3])
