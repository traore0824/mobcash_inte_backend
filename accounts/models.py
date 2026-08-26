import uuid
from django.db import models
from django.contrib.auth.models import AbstractUser

# from tinymce.models import HTMLField
from django.db.models import Sum
from .manager import UserManager
from crypto_fields import encrypt, decrypt


class AppName(models.Model):
    id = models.UUIDField(primary_key=True, editable=False, default=uuid.uuid4)
    name = models.CharField(
        max_length=100,
        unique=True,
    )
    image = models.TextField(blank=True, null=True)
    enable = models.BooleanField(default=True)

    # Champs chiffrés — stockés en clair dans la colonne DB mais accédés via property
    _hash = models.TextField(blank=True, null=True, db_column='hash')
    cashdeskid = models.CharField(blank=True, null=True, max_length=120)
    _cashierpass = models.TextField(blank=True, null=True, db_column='cashierpass')
    _betmomo_token = models.TextField(
        blank=True,
        null=True,
        db_column="betmomo_token",
        help_text="Token app dealer BetMomo (dat_...), chiffré.",
    )
    _betmomo_email = models.TextField(
        blank=True,
        null=True,
        db_column="betmomo_email",
        help_text="Email dealer BetMomo (chiffré) — login pour le solde.",
    )
    _betmomo_password = models.TextField(
        blank=True,
        null=True,
        db_column="betmomo_password",
        help_text="Mot de passe dealer BetMomo (chiffré) — login pour le solde.",
    )

    @property
    def hash(self):
        return decrypt(self._hash)

    @hash.setter
    def hash(self, value):
        self._hash = encrypt(value)

    @property
    def cashierpass(self):
        return decrypt(self._cashierpass)

    @cashierpass.setter
    def cashierpass(self, value):
        self._cashierpass = encrypt(value)

    @property
    def betmomo_token(self):
        return decrypt(self._betmomo_token)

    @betmomo_token.setter
    def betmomo_token(self, value):
        self._betmomo_token = encrypt(value)

    @property
    def betmomo_email(self):
        return decrypt(self._betmomo_email)

    @betmomo_email.setter
    def betmomo_email(self, value):
        self._betmomo_email = encrypt(value)

    @property
    def betmomo_password(self):
        return decrypt(self._betmomo_password)

    @betmomo_password.setter
    def betmomo_password(self, value):
        self._betmomo_password = encrypt(value)

    def get_betmomo_token(self) -> str:
        token = (self.betmomo_token or "").strip()
        if token:
            return token
        if self.is_betmomo_app:
            return (self.hash or "").strip()
        return ""

    def get_betmomo_email(self) -> str:
        return (self.betmomo_email or "").strip()

    def get_betmomo_password(self) -> str:
        return (self.betmomo_password or "").strip()

    @staticmethod
    def _normalize_app_name(name: str) -> str:
        return "".join(ch for ch in (name or "").lower() if ch.isalnum())

    @property
    def is_betmomo_app(self) -> bool:
        return self._normalize_app_name(self.name) in {"betmomo", "betpay", "bewallet"}

    @property
    def uses_betmomo(self) -> bool:
        """True si l'app est BetMomo et qu'un token dealer est configuré."""
        return self.is_betmomo_app and bool(self.get_betmomo_token())

    deposit_tuto_link = models.URLField(blank=True, null=True)
    withdrawal_tuto_link = models.URLField(blank=True, null=True)
    why_withdrawal_fail = models.URLField(blank=True, null=True)
    order = models.PositiveSmallIntegerField(blank=True, null=True)
    city = models.CharField(max_length=120, blank=True, null=True)
    street = models.CharField(max_length=124, null=True, blank=True)
    minimun_deposit = models.PositiveIntegerField(blank=True, null=True)
    max_deposit = models.PositiveIntegerField(blank=True, null=True)
    minimun_with = models.PositiveIntegerField(blank=True, null=True)
    max_win = models.PositiveIntegerField(blank=True, null=True)
    active_for_deposit = models.BooleanField(default=True)
    active_for_with = models.BooleanField(default=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "App name"
        verbose_name_plural = "App names"


class User(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    is_delete = models.BooleanField(default=False)
    phone = models.CharField(
        max_length=256,
        unique=False,
    )
    email = models.EmailField(unique=True, blank=True, null=True)
    otp = models.CharField(max_length=100, null=True)
    otp_created_at = models.DateTimeField(blank=True, null=True)
    is_block = models.BooleanField(default=False)
    password = models.CharField(max_length=255, null=True, blank=True)
    referrer_code = models.CharField(max_length=1000, blank=True, null=True)
    referral_code = models.CharField(max_length=100, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    is_supperuser = models.BooleanField(default=False)
    is_partner = models.BooleanField(default=False)
    public_key = models.CharField(max_length=255, blank=True, null=True, unique=True)
    secret_key = models.CharField(max_length=255, blank=True, null=True, unique=True)
    date_joined = models.DateTimeField(auto_now_add=True)
    last_login = models.DateTimeField(auto_now=True)
    can_publish_coupons = models.BooleanField(default=False)
    can_rate_coupons = models.BooleanField(default=False)
    coupon_points = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    password_save_db = models.CharField(max_length=255, blank=True, null=True)
    user_whatsapp_phone = models.CharField(max_length=20, blank=True, null=True)
    whatsapp_verified = models.BooleanField(default=False)
    user_telegram_username = models.CharField(max_length=150, blank=True, null=True)
    user_telegram_chat_id = models.CharField(max_length=124, blank=True, null=True)
    telegram_verified = models.BooleanField(default=False)
    sms_verified = models.BooleanField(default=False)

    @property
    def bonus_available(self):
        from mobcash_inte.models import Bonus

        bonus = (
            Bonus.objects.filter(bonus_with=False, bonus_delete=False, user=self ).aggregate(
                total=Sum("amount")
            )["total"]
            or 0
        )
        return bonus

    def full_name(self):
        return f"{self.last_name} {self.first_name}"

    class Meta:
        verbose_name = "User"
        verbose_name_plural = "Users"


class TelegramUser(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    telegram_user_id = models.CharField(max_length=100, unique=True)
    first_name = models.CharField(max_length=250, blank=True, null=True)
    last_name = models.CharField(max_length=250, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    is_block = models.BooleanField(default=False)

    def full_name(self):
        return f"{self.last_name} {self.first_name}"

    @property
    def fullname(self):
        return f"{self.last_name} {self.first_name}"


class Advertisement(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    image = models.TextField(blank=True, null=True)
    # content = models.TextField()
    enable = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Advertisement"
        verbose_name_plural = "Advertisements"

    def __str__(self):
        return str(self.id)
