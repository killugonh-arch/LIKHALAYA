from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.db.models import Q

UserModel = get_user_model()


class UsernameOrEmailBackend(ModelBackend):
    """Authenticate using either the username or the email address.

    Falls back to the normal ModelBackend behaviour (username only) if
    something unexpected happens, so existing logins keep working.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None:
            username = kwargs.get(UserModel.USERNAME_FIELD)
        if username is None or password is None:
            return None

        try:
            # CustomUser.objects excludes archived accounts by design;
            # that's the manager we want to check against here.
            user = UserModel.objects.get(
                Q(username__iexact=username) | Q(email__iexact=username)
            )
        except UserModel.DoesNotExist:
            # Run the default password hasher to mitigate user-enumeration
            # timing attacks, same trick Django's ModelBackend uses.
            UserModel().set_password(password)
            return None
        except UserModel.MultipleObjectsReturned:
            # Extremely unlikely (would mean two active accounts share an
            # email), but if it happens, prefer an exact username match.
            user = UserModel.objects.filter(username__iexact=username).first()
            if user is None:
                return None

        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None