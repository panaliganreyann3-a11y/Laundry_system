const orderConfig = window.orderConfig || {};

function updateSummary() {
  const weight = parseFloat(document.getElementById('weightInput').value) || 0;
  const isRush = document.getElementById('priorityToggle').checked;
  const base = weight * (orderConfig.pricePerKg || 30);
  const total = base + (isRush ? (orderConfig.rushSurcharge || 50) : 0);
  const customerId = document.getElementById('customerSelect').value;

  document.getElementById('summaryWeight').textContent = weight > 0 ? weight.toFixed(1) + ' kg' : '- kg';
  document.getElementById('summaryBase').textContent = 'PHP ' + base.toFixed(2);
  document.getElementById('totalVal').textContent = 'PHP ' + total.toFixed(2);
  document.getElementById('totalVal').dataset.raw = total.toFixed(2);
  document.getElementById('summaryCustomer').textContent = orderConfig.customerNames?.[customerId] || '-';
  document.getElementById('rushRow').style.display = isRush ? 'flex' : 'none';

  const hrs = isRush ? 2 : 24;
  const pickup = new Date(Date.now() + hrs * 3600000);
  document.getElementById('pickupTime').textContent =
    pickup.toLocaleDateString('en-PH', {month:'short', day:'numeric'}) + ', ' +
    pickup.toLocaleTimeString('en-PH', {hour:'2-digit', minute:'2-digit'});

  const isPaid = document.getElementById('paymentSelect').value === 'PAID';
  document.getElementById('payBadge').innerHTML = isPaid
    ? '<span class="badge bg-success-subtle text-success border border-success-subtle px-3 py-2"><i class="bi bi-check-circle me-1"></i>Paid - PHP ' + total.toFixed(2) + '</span>'
    : '<span class="badge bg-danger-subtle text-danger border border-danger-subtle px-3 py-2"><i class="bi bi-clock me-1"></i>Payment on Pickup</span>';
}

function toggleAmountPaid() {
  document.getElementById('amountDiv').style.display =
    document.getElementById('paymentSelect').value === 'PAID' ? 'block' : 'none';
}

document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('input[name="service_type"]').forEach((radio) => {
    radio.addEventListener('change', function() {
      document.querySelectorAll('input[name="service_type"]').forEach((item) => {
        item.nextElementSibling.querySelector('.check-icon').classList.add('d-none');
        item.nextElementSibling.classList.remove('btn-primary', 'text-white');
      });
      this.nextElementSibling.querySelector('.check-icon').classList.remove('d-none');
      this.nextElementSibling.classList.add('btn-primary', 'text-white');
      document.getElementById('summaryService').textContent = orderConfig.serviceLabels?.[this.value] || '';
      updateSummary();
    });
  });
  updateSummary();
  document.getElementById('queueBadge').textContent = 'Queue will be assigned on submit';
});
