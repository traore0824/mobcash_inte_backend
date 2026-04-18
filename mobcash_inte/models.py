import uuid

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
API_CHOICES = [("connect", "Blaffa Connect"), ("feexpay", "feexpay")]


class Network(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    name = models.CharField(
        max_length=100, blank=True, null=True, choices=NETWORK_CHOICES
    )
    customer_pay_fee = models.BooleanField(default=True)
    placeholder = models.CharField(blank=True, null=True, max_length=100)
    public_name = models.CharField(max_length=100, blank=True, null=True, unique=True)
    country_code = models.CharField(max_length=100, blank=True, null=True)
    indication = models.CharField(max_length=100, blank=True, null=True)
    image = models.TextField(blank=True, null=True)
    withdrawal_message = models.TextField( blank=True, null=True)
    deposit_api = models.CharField(
        max_length=100, choices=API_CHOICES, default="connect"
    )
    withdrawal_api = models.CharField(
        max_length=100, choices=API_CHOICES, default="connect"
    )
    payment_by_link = models.BooleanField(default=False)
    payment_by_ussd_code = models.BooleanField(default=False)
    otp_required = models.BooleanField(default=False)
    deposit_message = models.TextField(blank=True, null=True)
    active_for_deposit = models.BooleanField(default=True)
    active_for_with = models.BooleanField(default=True)
    manual_processing = models.BooleanField(default=False)
    ussd_code = models.CharField(max_length=200, blank=True, null=True)
    reduce_fee = models.BooleanField(default=False)
    fee_payin = models.DecimalField(decimal_places=2, max_digits=10, blank=True, null=True)


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
    telegram = models.CharField(blank=True, null=True, max_length=500)
    moov_marchand_phone = models.CharField(max_length=250, blank=True, null=True)
    mtn_marchand_phone = models.CharField(max_length=250, blank=True, null=True)
    orange_marchand_phone = models.CharField(max_length=250, blank=True, null=True)
    connect_pro_base_url = models.URLField(blank=True, null=True)

    bf_moov_marchand_phone = models.CharField(max_length=250, blank=True, null=True)
    mobcash_api_key = models.URLField(blank=True, null=True)
    mobcash_api_secret = models.URLField(blank=True, null=True)
    bf_orange_marchand_phone = models.CharField(max_length=250, blank=True, null=True)
    requires_deposit_to_view_coupon = models.BooleanField(default=False)
    minimun_deposit_before_view_coupon = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    max_coupons_per_day = models.PositiveIntegerField(default=10)
    max_coupons_per_week = models.PositiveIntegerField(default=50)
    enable_coupon_monetization = models.BooleanField(default=False)
    minimum_coupon_withdrawal = models.DecimalField(max_digits=10, decimal_places=2, default=1000.00)
    monetization_amount = models.DecimalField(max_digits=10, decimal_places=2, default=1.00)
    coupon_rating_points = models.DecimalField(max_digits=4, decimal_places=2, default=1.0)
    payout_mode = models.CharField(max_length=20, choices=[('immediate', 'Immédiat'), ('monthly', 'Mensuel')], default='monthly')
    min_withdrawal = models.DecimalField(max_digits=10, decimal_places=2, default=10.00)
    max_withdrawal_monthly = models.DecimalField(max_digits=10, decimal_places=2, default=500.00)
    auto_approve_withdrawal = models.BooleanField(default=False)
    coupon_enable = models.BooleanField(default=False)
    allow_all_users_publish_coupons = models.BooleanField(default=False)

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
    ("timeouf", "timeouf"),
    ("annuler", "Annuler"),
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
    message = models.TextField(default="Transaction en cours", blank=True, null=True)
    transaction_link = models.TextField(blank=True, null=True)
    net_payable_amout = models.PositiveIntegerField(blank=True, null=True)
    otp_code = models.CharField(max_length=20, blank=True, null=True)
    public_id = models.CharField(max_length=250, blank=True, null=True)
    already_process = models.BooleanField(default=False)
    source = models.CharField(
        max_length=120, blank=True, null=True, choices=SOURCE_CHOICE
    )
    payout_started = models.BooleanField(default=False)
    payout_done = models.BooleanField(default=False)

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
    event_send= models.BooleanField(default=False)
    fond_calculate = models.BooleanField(default=False)
    all_status = models.JSONField(default=list, blank=True)
    fixed_by_admin = models.BooleanField(default=False)
    mobcash_response = models.TextField(blank=True, null=True)
    ussd_code = models.CharField(max_length=200, blank=True, null=True)
    connect_pro_response = models.TextField(blank=True, null=True)
    credit_used = models.PositiveIntegerField(default=0)

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
    class Status(models.TextChoices):
        PENDING = "pending", "En attente"
        PROCESSING = "processing", "En cours"
        SUCCESS = "success", "Succès"
        FAILED = "failed", "Échec"

    created_at = models.DateTimeField(auto_now_add=True)
    webhook_data = models.JSONField(default=dict)
    api = models.CharField(max_length=100)
    reference = models.CharField(max_length=255, blank=True, null=True)
    header = models.TextField(blank=True, null=True)

    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING
    )
    processed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)
    processed = models.BooleanField(default=False)


class Coupon(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    bet_app = models.ForeignKey(
        AppName, on_delete=models.CASCADE, blank=True, null=True
    )
    code = models.CharField(max_length=150, blank=True, null=True)

    def __str__(self):
        return str(self.id)


class TestModel(models.Model):
    name = models.TextField(blank=True, null=True)

    def __str__(self):
        return str(self.name)

    class Meta:
        verbose_name = "Test Model"
        verbose_name_plural = "Test Models"


PAYMENT_METHOD_CHOICES = [
    ("MOBILE_MONEY", "Mobile Money"),
    ("BANK_TRANSFER", "Bank Transfer"),
    ("OTHER", "Other"),
]


PARTNER_TRANS_STATUS = [
    ("pending", "Pending"),
    ("accept", "Accept"),
    ("failed", "Failed"),
    ("annuler", "Annulé"),
]

PARTNER_TRANS_TYPE = [
    ("deposit", "Dépôt"),
    ("withdrawal", "Retrait"),
]


class PartnerTransaction(models.Model):
    partner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="partner_transactions")
    app = models.ForeignKey(AppName, on_delete=models.CASCADE)
    reference = models.CharField(max_length=255, unique=True)
    external_reference = models.CharField(max_length=255, blank=True, null=True)
    type_trans = models.CharField(max_length=50, choices=PARTNER_TRANS_TYPE)
    status = models.CharField(max_length=50, choices=PARTNER_TRANS_STATUS, default="pending")
    amount = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True)
    user_app_id = models.CharField(max_length=120)
    withdriwal_code = models.CharField(max_length=50, blank=True, null=True)
    bet_response = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    validated_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        verbose_name = "Partner Transaction"
        verbose_name_plural = "Partner Transactions"
        ordering = ["-created_at"]

    def __str__(self):
        return self.reference


class RechargeMobcashBalance(models.Model):
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(
        max_length=50, choices=PAYMENT_METHOD_CHOICES, default="MOBILE_MONEY"
    )
    payment_reference = models.CharField(max_length=255)
    notes = models.TextField(blank=True, null=True, default="Aucune note n'a ete enregistrer")
    payment_proof = models.URLField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True
    )

    class Meta:
        verbose_name = "Recharge Mobcash Balance"
        verbose_name_plural = "Recharge Mobcash Balances"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Recharge {self.payment_reference} - {self.amount}"


class UserCredit(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='credit')
    amount = models.PositiveIntegerField(default=0)
    note = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Crédit utilisateur"
        verbose_name_plural = "Crédits utilisateurs"

    def __str__(self):
        return f"UserCredit({self.user}, {self.amount} FCFA)"


class CouponV2(models.Model):
    COUPON_TYPES = [
        ('single', 'Paris simple'),
        ('combine', 'Paris combiné'),
        ('system', 'Système'),
    ]
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    bet_app = models.ForeignKey(AppName, on_delete=models.CASCADE, blank=True, null=True)
    code = models.CharField(max_length=150, blank=True, null=True)
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='published_coupons_v2', blank=True, null=True)
    likes_count = models.PositiveIntegerField(default=0)
    dislikes_count = models.PositiveIntegerField(default=0)
    coupon_type = models.CharField(max_length=20, choices=COUPON_TYPES, default='combine')
    cote = models.DecimalField(max_digits=6, decimal_places=2, default=1.00)
    match_count = models.PositiveIntegerField(default=1)
    potential_gain = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Coupon V2"
        verbose_name_plural = "Coupons V2"

    def __str__(self):
        return str(self.id)


class CouponRatingV2(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    coupon = models.ForeignKey(CouponV2, on_delete=models.CASCADE, related_name='ratings')
    is_like = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['user', 'coupon']
        verbose_name = "Vote Coupon V2"
        verbose_name_plural = "Votes Coupon V2"

    def __str__(self):
        return str(self.id)


class CouponWallet(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='coupon_wallet')
    balance = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_earned = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    pending_payout = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Portefeuille Coupon"
        verbose_name_plural = "Portefeuilles Coupon"

    def __str__(self):
        return f"Wallet({self.user}, {self.balance} FCFA)"


COUPON_PAYOUT_STATUS = [
    ('pending', 'En attente'),
    ('processing', 'En cours'),
    ('completed', 'Terminé'),
    ('failed', 'Échec'),
    ('cancelled', 'Annulé'),
]

COUPON_PAYOUT_TYPE = [
    ('automatic', 'Automatique - Seuil atteint'),
    ('monthly', 'Paiement mensuel'),
    ('manual', 'Manuel admin'),
]


class CouponPayout(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    wallet = models.ForeignKey(CouponWallet, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payout_type = models.CharField(max_length=20, choices=COUPON_PAYOUT_TYPE)
    status = models.CharField(max_length=20, choices=COUPON_PAYOUT_STATUS, default='pending')
    processed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    payment_method = models.CharField(max_length=50, default='bank_transfer')
    transaction_id = models.CharField(max_length=100, null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = "Versement Coupon"
        verbose_name_plural = "Versements Coupon"
        ordering = ['-created_at']

    def __str__(self):
        return str(self.id)


COUPON_WITHDRAWAL_STATUS = [
    ('pending', 'En attente'),
    ('approved', 'Approuvé'),
    ('rejected', 'Rejeté'),
    ('completed', 'Terminé'),
]


class CouponWithdrawal(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    wallet = models.ForeignKey(CouponWallet, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=COUPON_WITHDRAWAL_STATUS, default='pending')
    bank_name = models.CharField(max_length=100)
    account_number = models.CharField(max_length=50)
    account_holder = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    admin_notes = models.TextField(blank=True)

    class Meta:
        verbose_name = "Retrait Coupon"
        verbose_name_plural = "Retraits Coupon"
        ordering = ['-created_at']

    def __str__(self):
        return str(self.id)


class AuthorComment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='comments_written')
    coupon_author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='comments_received')
    coupon = models.ForeignKey(CouponV2, on_delete=models.CASCADE, related_name='comments', null=True, blank=True)
    content = models.TextField()
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='replies')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_deleted = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Commentaire Auteur"
        verbose_name_plural = "Commentaires Auteur"
        indexes = [
            models.Index(fields=['coupon_author', 'created_at']),
            models.Index(fields=['parent', 'created_at']),
        ]

    def __str__(self):
        return str(self.id)


class AuthorCouponRating(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='ratings_given')
    coupon_author = models.ForeignKey(User, on_delete=models.CASCADE, related_name='ratings_received')
    coupon = models.ForeignKey(CouponV2, on_delete=models.CASCADE, related_name='author_ratings', null=True, blank=True)
    is_like = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['user', 'coupon_author']
        verbose_name = "Vote Auteur"
        verbose_name_plural = "Votes Auteur"

    def __str__(self):
        return str(self.id)
