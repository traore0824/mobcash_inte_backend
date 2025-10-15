from rest_framework.permissions import BasePermission
from django.contrib.auth.models import AnonymousUser
from mobcash_inte.models import TelegramUser  # change selon ton projet


class IsAuthenticated(BasePermission):
    def has_permission(self, request, view):
        # ✅ Cas 1 : utilisateur Django standard authentifié
        if request.user and request.user.is_authenticated:
            return True

        # ✅ Cas 2 : utilisateur Telegram via header
        user_id = request.headers.get("X-USER-ID")
        if not user_id:
            return False

        user = TelegramUser.objects.filter(
            telegram_user_id=user_id, is_block=False
        ).first()

        if not user:
            return False
        request.telegram_user = user
        return True
