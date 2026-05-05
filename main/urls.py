from django.contrib import admin
from django.urls import include, path
from django.conf import settings
from django.conf.urls.static import static


urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('accounts.urls')),
    path('', include('customers.urls')),
    path('', include('admin_portal.urls')),
    path('', include('staff_portal.urls')),
    path('', include('laundry.urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
