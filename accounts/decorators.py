from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def manager_required(view):
    """Only township management may open this page."""

    @wraps(view)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not request.user.is_manager:
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return wrapper
