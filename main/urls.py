from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views
from django.conf import settings
from django.conf.urls.static import static
from laundry import views as laundry_views

urlpatterns = [
    path('admin/', admin.site.urls),

    # ── Login pages ──
    path('admin-login/', laundry_views.admin_login, name='admin_login'),
    path('staff-login/', laundry_views.staff_login, name='staff_login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),

    # ── App ──
    path('', include('laundry.urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)