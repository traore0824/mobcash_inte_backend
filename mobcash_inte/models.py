from django.db import models

from accounts.models import AppName, TelegramUser, User


class UploadFile(models.Model):
    file = models.FileField(upload_to="media", blank=True, null=True)

    class Meta:
        verbose_name = "Upload File"
        verbose_name_plural = "Upload Files"

    def __str__(self):
        return str(self.id)

    class Meta:
        verbose_name = "championnat"
        verbose_name_plural = "championnats"


class Advertisement(models.Model):
    image = models.TextField(blank=True, null=True)
    # content = models.TextField()
    enable = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Advertisement"
        verbose_name_plural = "Advertisements"

    def __str__(self):
        return str(self.id)


class Caisse(models.Model):
    solde = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    updated_at = models.DateTimeField(blank=True, null=True)
    bet_app = models.ForeignKey(AppName, on_delete=models.CASCADE)

    class Meta:
        verbose_name = "Solde"
        verbose_name_plural = "Soldes"


class UserLimite(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    updated_date = models.DateTimeField(auto_now_add=True)
    amount = models.PositiveBigIntegerField(default=0)


class Deposit(models.Model):
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    bet_app = models.ForeignKey(AppName, on_delete=models.CASCADE)

    class Meta:
        verbose_name = "Deposit"
        verbose_name_plural = "Deposits"

    def __str__(self):
        return str(self.id)


class IDLink(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, blank=True, null=True)
    telegram_user = models.ForeignKey(
        TelegramUser, models.CASCADE, blank=True, null=True
    )
    user_app_id = models.CharField(max_length=120)
    app_name = models.ForeignKey(
        AppName, on_delete=models.CASCADE, blank=True, null=True
    )
    created_at = models.DateTimeField(auto_now_add=True, null=True)

    class Meta:
        verbose_name = "ID Link"
        verbose_name_plural = "ID Links"


class Notification(models.Model):
    reference = models.CharField(max_length=150, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    content = models.TextField()
    is_read = models.BooleanField(default=False)
    title = models.CharField(max_length=100, blank=True, null=True)

    def total_unread_notification(self, user):
        return Notification.objects.filter(user=user, is_read=False).count()


NETWORK_CHOICES = [
    ("mtn", "MTN"),
    ("moov", "MOOV"),
    ("card", "Cart"),
    ("sbin", "Celtis"),
    ("orange", "Orange"),
    ("wave", "wave"),
    ("togocom", "Togocom"),
    ("airtel", "Airtel"),
    ("mpesa", "Mpsesa"),
    ("afrimoney", "Afrimoney"),
]
API_CHOICES = [
    ("connect", "Blaffa Connect"),
]


class Network(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    name = models.CharField(
        max_length=100, blank=True, null=True, choices=NETWORK_CHOICES
    )
    placeholder = models.CharField(blank=True, null=True, max_length=100)
    public_name = models.CharField(max_length=100, blank=True, null=True, unique=True)
    country_code = models.CharField(max_length=100, blank=True, null=True)
    indication = models.CharField(max_length=100, blank=True, null=True)
    image = models.TextField(blank=True, null=True)
    withdrawal_message = models.CharField(max_length=150, blank=True, null=True)
    deposit_api = models.CharField(
        max_length=100, choices=API_CHOICES, default="connect"
    )
    withdrawal_api = models.CharField(
        max_length=100, choices=API_CHOICES, default="connect"
    )
    payment_by_link = models.BooleanField(default=False)
    otp_required = models.BooleanField(default=False)
    deposit_message = models.TextField(blank=True, null=True)
    active_for_deposit = models.BooleanField(default=True)
    active_for_with = models.BooleanField(default=True)


class Setting(models.Model):
    minimum_deposit = models.DecimalField(max_digits=10, decimal_places=2)
    minimum_withdrawal = models.DecimalField(max_digits=10, decimal_places=2)
    bonus_percent = models.DecimalField(max_digits=4, decimal_places=2)
    reward_mini_withdrawal = models.DecimalField(
        max_digits=10, decimal_places=2, default=500.00
    )
    whatsapp_phone = models.CharField(max_length=254, blank=True, null=True)
    minimum_solde = models.DecimalField(
        max_digits=12, decimal_places=2, blank=True, null=True
    )
    referral_bonus = models.BooleanField(default=True)
    deposit_reward = models.BooleanField(default=True)
    deposit_reward_percent = models.DecimalField(
        max_digits=10, decimal_places=2, default=1.00
    )
    min_version = models.PositiveSmallIntegerField(blank=True, null=True)
    last_version = models.PositiveSmallIntegerField(blank=True, null=True)
    dowload_apk_link = models.URLField(blank=True, null=True)
    wave_default_link = models.URLField(blank=True, null=True)
    connect_pro_password = models.CharField(max_length=250, blank=True, null=True)
    connect_pro_email = models.CharField(max_length=250, blank=True, null=True)
    connect_pro_token = models.TextField(blank=True, null=True)
    connect_pro_refresh = models.TextField(blank=True, null=True)
    expired_connect_pro_token = models.DateTimeField(blank=True, null=True)
    orange_default_link = models.URLField(blank=True, null=True)
    mtn_default_link = models.URLField(blank=True, null=True)

    def __str__(self):
        return str(self.id)


TYPE_TRANS = [
    ("deposit", "Dépôt"),
    ("withdrawal", "Retrait"),
    ("disbursements", "Disbursements"),
    ("reward", "reward"),
]

TRANS_STATUS = [
    ("init_payment", "Une etape sur 2"),
    ("accept", "Accept"),
    ("error", "Erreur"),
    ("pending", "Pendind"),
    ("timeouf", "timeouf")
]


SOURCE_CHOICE = [("mobile", "Mobile"), ("web", "Web"), ("bot", "bot")]


class Transaction(models.Model):
    amount = models.PositiveIntegerField(blank=True, null=True)
    deposit_reward_amount = models.PositiveIntegerField(blank=True, null=True)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    telegram_user = models.ForeignKey(
        TelegramUser, on_delete=models.SET_NULL, null=True, blank=True
    )
    reference = models.CharField(max_length=255, blank=True, null=True)

    type_trans = models.CharField(max_length=120, choices=TYPE_TRANS)
    status = models.CharField(max_length=120, choices=TRANS_STATUS, default="pending")
    created_at = models.DateTimeField(auto_now_add=True)
    validated_at = models.DateTimeField(blank=True, null=True)
    webhook_data = models.TextField(blank=True, null=True)
    wehook_receive_at = models.DateTimeField(blank=True, null=True)
    phone_number = models.CharField(max_length=50, blank=True, null=True)
    app = models.ForeignKey(AppName, on_delete=models.CASCADE, blank=True, null=True)
    user_app_id = models.CharField(max_length=120, blank=True, null=True)
    withdriwal_code = models.CharField(max_length=50, blank=True, null=True)
    error_message = models.TextField(blank=True, null=True)
    transaction_link = models.TextField(blank=True, null=True)
    net_payable_amout = models.PositiveIntegerField(blank=True, null=True)
    otp_code = models.CharField(max_length=20, blank=True, null=True)
    public_id = models.CharField(max_length=250, blank=True, null=True)
    already_process = models.BooleanField(default=False)
    source = models.CharField(
        max_length=120, blank=True, null=True, choices=SOURCE_CHOICE
    )
    network = models.ForeignKey(
        Network, on_delete=models.CASCADE, blank=True, null=True
    )
    old_status  = models.CharField(
        max_length=120, choices=TRANS_STATUS, default="pending"
    )
    old_public_id = models.CharField(
        max_length=120, choices=TRANS_STATUS, default="pending"
    )
    success_webhook_send = models.BooleanField(default=False)
    fail_webhook_send = models.BooleanField(default=False)
    pending_webhook_send = models.BooleanField(default=False)
    timeout_webhook_send = models.BooleanField(default=False)
    api = models.CharField(max_length=100, blank=True, null=True)

    class Meta:
        verbose_name = "Transaction"
        verbose_name_plural = "Transactions"
        ordering = ["-created_at"]

    def __str__(self):
        return str(self.id)


class Bonus(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    transaction = models.ForeignKey(Transaction, on_delete=models.CASCADE, blank=True, null=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    reason_bonus = models.CharField(max_length=255)
    bonus_with = models.BooleanField(default=False)
    bonus_delete = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Bonus"
        verbose_name_plural = "Bonuss"


class Reward(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    def referral_code(self):
        return self.user.referral_code

    def share_link(self):
        return f"Utilisez le code {self.user.referral_code} pour bénéficier d'avantages exclusifs sur Coobet. Effectuez vos dépôts et retraits 1xbet de façon instantanée et bénéficiez de 2'%' sur chaque dépôt effectué par votre filiale. Téléchargez l'application maintenant et partagez le plaisir avec vos proches ! 📲 Lien pour télécharger l'application :\n 👉 {Setting.objects.first().dowload_apk_link}"

    def __str__(self):
        return str(self.id)

    class Meta:
        verbose_name = "Recompense"
        verbose_name_plural = "Recompenses"


class BotMessage(models.Model):
    content = models.CharField(max_length=250)
    chat = models.CharField(max_length=100)


class UserPhone(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(User, models.CASCADE, blank=True, null=True)
    telegram_user = models.ForeignKey(
        TelegramUser, models.CASCADE, blank=True, null=True
    )
    phone = models.CharField(max_length=120)
    network = models.ForeignKey(
        Network, on_delete=models.CASCADE, blank=True, null=True
    )

class WebhookLog(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    webhook_data = models.JSONField(default=dict)
    api = models.CharField(max_length=100)
    reference = models.CharField(max_length=255, blank=True, null=True)
    header = models.TextField(blank=True, null=True)    # Create your models here.


class Coupon(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    bet_app = models.ForeignKey(
        AppName, on_delete=models.CASCADE, blank=True, null=True
    )
    code = models.CharField(max_length=150, blank=True, null=True)

    def __str__(self):
        return str(self.id)
