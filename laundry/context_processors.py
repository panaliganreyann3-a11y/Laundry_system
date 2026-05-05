from django.core.exceptions import ObjectDoesNotExist

from .models import SiteSettings


def layout_settings(request):
    profile = None
    if getattr(request, 'user', None) and request.user.is_authenticated:
        try:
            profile = request.user.profile
        except ObjectDoesNotExist:
            profile = None
    return {
        'site_settings': SiteSettings.load(),
        'current_profile': profile,
    }
