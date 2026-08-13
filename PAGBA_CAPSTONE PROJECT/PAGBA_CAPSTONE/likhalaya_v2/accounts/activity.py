"""
Helpers for recording staff/user activity (logins, logouts, and staff actions
taken in the dashboard) into accounts.models.ActivityLog.
"""


def get_client_ip(request):
    """Best-effort client IP, respecting a reverse proxy's X-Forwarded-For."""
    if not request:
        return None
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def log_activity(request, action, description='', user=None, resource='', resource_label='',
                  previous_value='', new_value='', status='success'):
    """
    Create an ActivityLog entry.

    `user` can be passed explicitly (e.g. from an auth signal where
    request.user may not yet be populated); otherwise it's taken from
    request.user.

    `resource` / `resource_label` identify what was affected (e.g.
    resource='Product', resource_label='Handwoven Basket'). `previous_value`
    / `new_value` capture a before/after snapshot for updates (e.g. an order
    status change). `status` is 'success' or 'failed'.
    """
    from .models import ActivityLog

    if user is None:
        user = getattr(request, 'user', None)
        if user is not None and not user.is_authenticated:
            user = None

    ActivityLog.objects.create(
        user=user,
        username=getattr(user, 'username', '') or '',
        role=getattr(user, 'role', '') or '',
        action=action,
        description=description,
        resource=resource,
        resource_label=resource_label,
        previous_value=previous_value,
        new_value=new_value,
        status=status,
        ip_address=get_client_ip(request),
    )