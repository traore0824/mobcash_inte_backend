from django.contrib import admin

from accounts.models import Advertisement
from .models import Bonus, Caisse, Coupon, IDLink, Network, Notification, RechargeMobcashBalance, Reward, Setting, TestModel, Transaction, UserPhone, WebhookLog


@admin.register(Network)
class NetworkAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "public_name",
        "country_code",
        "deposit_api",
        "withdrawal_api",
        "payment_by_link",
        "otp_required",
        "active_for_deposit",
        "active_for_with",
        "customer_pay_fee",
        "manual_processing",
        "created_at",
    )
    list_filter = (
        "deposit_api",
        "withdrawal_api",
        "otp_required",
        "payment_by_link",
        "active_for_deposit",
        "active_for_with",
        "customer_pay_fee",
        "manual_processing",
        "country_code",
    )
    search_fields = (
        "name",
        "public_name",
        "country_code",
        "placeholder",
        "indication",
    )
    ordering = ("-created_at",)
    readonly_fields = ("created_at",)
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "name",
                    "public_name",
                    "country_code",
                    "placeholder",
                    "indication",
                    "image",
                    "deposit_message",
                    "withdrawal_message",
                )
            },
        ),
        (
            "APIs & Options",
            {
                "fields": (
                    "deposit_api",
                    "withdrawal_api",
                    "payment_by_link",
                    "payment_by_ussd_code",
                    "otp_required",
                    "reduce_fee",
                    "ussd_code",
                    "fee_payin",
                    "customer_pay_fee",
                    "manual_processing",
                )
            },
        ),
        (
            "Activation",
            {
                "fields": (
                    
                    "active_for_deposit",
                    "active_for_with",
                )
            },
        ),
        (
            "Metadata",
            {
                "fields": ("created_at",),
            },
        ),
    )


@admin.register(UserPhone)
class UserPhoneAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "phone",
        "user_display",
        "telegram_user_display",
        "network",
        "created_at",
    )
    list_filter = (
        "network",
        "created_at",
    )
    search_fields = (
        "phone",
        "user__email",
        "user__first_name",
        "user__last_name",
        "telegram_user__telegram_user_id",
        "telegram_user__first_name",
        "telegram_user__last_name",
    )
    ordering = ("-created_at",)
    readonly_fields = ("created_at",)

    def user_display(self, obj):
        if not obj.user:
            return f"{obj.telegram_user.first_name} {obj.telegram_user.last_name} ({obj.telegram_user.email})"
        return f"{obj.user.first_name} {obj.user.last_name} ({obj.user.email})"

    user_display.short_description = "User"

    def telegram_user_display(self, obj):
        if obj.telegram_user:
            return (
                f"{obj.telegram_user.fullname} ({obj.telegram_user.telegram_user_id})"
            )
        return "—"

    telegram_user_display.short_description = "Telegram User"


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("title", "user", "is_read", "created_at", "reference")
    list_filter = ("is_read", "created_at")
    search_fields = ("title", "content", "reference", "user__email", "user__phone")
    ordering = ("-created_at",)
    autocomplete_fields = ("user",)
    readonly_fields = ("created_at",)

    fieldsets = (
        (None, {"fields": ("user", "title", "content", "reference", "is_read")}),
        (
            "Metadata",
            {
                "fields": ("created_at",),
            },
        ),
    )


@admin.register(Setting)
class SettingAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "minimum_deposit",
        "minimum_withdrawal",
        "bonus_percent",
        "referral_bonus",
        "deposit_reward",
        "deposit_reward_percent",
        "min_version",
        "moov_marchand_phone",
    )

    search_fields = ("whatsapp_phone", "connect_pro_email")
    list_filter = ("referral_bonus", "deposit_reward")
    readonly_fields = ("id",)
    fieldsets = (
        (
            "Montants minimaux",
            {
                "fields": (
                    "minimum_deposit",
                    "minimum_withdrawal",
                    "reward_mini_withdrawal",
                    "minimum_solde",
                )
            },
        ),
        (
            "Bonus et Récompenses",
            {
                "fields": (
                    "bonus_percent",
                    "referral_bonus",
                    "deposit_reward",
                    "deposit_reward_percent",
                    "requires_deposit_to_view_coupon",
                    "minimun_deposit_before_view_coupon",
                )
            },
        ),
        (
            "Versions et APK",
            {
                "fields": (
                    "min_version",
                    "last_version",
                    "dowload_apk_link",
                )
            },
        ),
        (
            "Réseaux par défaut & Marchands",
            {
                "fields": (
                    "wave_default_link",
                    "orange_default_link",
                    "mtn_default_link",
                    "moov_marchand_phone",
                    "mtn_marchand_phone",
                    "orange_marchand_phone",
                    "bf_moov_marchand_phone",
                    "bf_orange_marchand_phone",
                )
            },
        ),
        (
            "WhatsApp & Social",
            {
                "fields": (
                    "whatsapp_phone",
                    "telegram",
                )
            },
        ),
        (
            "Connect Pro",
            {
                "fields": (
                    "connect_pro_email",
                    "connect_pro_password",
                    "connect_pro_token",
                    "connect_pro_refresh",
                    "expired_connect_pro_token",
                    "connect_pro_base_url",
                )
            },
        ),
        (
            "Mobcash API",
            {
                "fields": (
                    "mobcash_api_key",
                    "mobcash_api_secret",
                )
            },
        ),
    )


@admin.register(Bonus)
class BonusAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "amount",
        "reason_bonus",
        "bonus_with",
        "bonus_delete",
        "created_at",
    )
    list_filter = ("bonus_with", "bonus_delete", "created_at")
    search_fields = ("user__username", "user__email", "reason_bonus")
    date_hierarchy = "created_at"
    ordering = ("-created_at",)


@admin.register(Caisse)
class CaisseAdmin(admin.ModelAdmin):
    list_display = ("bet_app", "solde", "updated_at")
    list_filter = ("bet_app",)
    search_fields = ("bet_app__name",)
    readonly_fields = ("updated_at",)
    autocomplete_fields = ("bet_app",)

    fieldsets = (
        (None, {"fields": ("bet_app", "solde")}),
        ("Mise à jour", {"fields": ("updated_at",)}),
    )

# admin.site.register(Transaction)


@admin.register(WebhookLog)
class WebhookLogAdmin(admin.ModelAdmin):
    list_display = ("id", "api", "reference", "created_at")
    list_filter = ("api", "created_at")
    search_fields = ("api", "reference")
    readonly_fields = ("created_at",)
    ordering = ("-created_at",)


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "telegram_user",
        "amount",
        "status",
        "type_trans",
        "api",
        "reference",
        "created_at",
        "validated_at",
    )
    list_filter = (
        "status",
        "type_trans",
        "api",
        "source",
        "network",
        "created_at",
    )
    search_fields = (
        "reference",
        "phone_number",
        "public_id",
    )
    readonly_fields = (
        "created_at",
        "validated_at",
        "wehook_receive_at",
        "webhook_data",
        "mobcash_response",
        "error_message",
        "transaction_link",
        "all_status",
    )
    ordering = ("-created_at",)
    date_hierarchy = "created_at"
    autocomplete_fields = ("user", "app", "network")

    fieldsets = (
        (
            "Informations de base",
            {
                "fields": (
                    "user",
                    "telegram_user",
                    "amount",
                    "net_payable_amout",
                    "deposit_reward_amount",
                    "reference",
                    "public_id",
                    "user_app_id",
                    "phone_number",
                )
            },
        ),
        (
            "Type & Statut",
            {
                "fields": (
                    "type_trans",
                    "status",
                    "source",
                    "api",
                    "network",
                    "app",
                    "withdriwal_code",
                    "otp_code",
                )
            },
        ),
        (
            "Suivi Webhook & État interne",
            {
                "fields": (
                    "already_process",
                    "payout_started",
                    "payout_done",
                    "event_send",
                    "fond_calculate",
                    "fixed_by_admin",
                )
            },
        ),
        (
            "Confirmation Webhook (Booléens)",
            {
                "fields": (
                    "success_webhook_send",
                    "fail_webhook_send",
                    "pending_webhook_send",
                    "timeout_webhook_send",
                )
            },
        ),
        (
            "Historique & Logs",
            {
                "fields": (
                    "all_status",
                    "webhook_data",
                    "mobcash_response",
                    "error_message",
                    "message",
                    "transaction_link",
                )
            },
        ),
        (
            "Dates",
            {
                "fields": (
                    "created_at",
                    "validated_at",
                    "wehook_receive_at",
                )
            },
        ),
    )


@admin.register(Reward)
class RewardAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "amount",
        "referral_code_display",
        "share_link_display",
    )
    search_fields = ("user__username", "user__email", "user__referral_code")
    list_filter = ("user",)
    readonly_fields = ("referral_code_display", "share_link_display")

    # Pour afficher le code de parrainage dans l'admin
    def referral_code_display(self, obj):
        return obj.referral_code()

    referral_code_display.short_description = "Code de parrainage"

    # Pour afficher le lien de partage dans l'admin
    def share_link_display(self, obj):
        return obj.share_link()

    share_link_display.short_description = "Lien de partage"

    # Optionnel : si tu veux rendre les liens cliquables
    def share_link_display(self, obj):
        return f'<a href="{obj.share_link()}" target="_blank">Voir le lien</a>'

    share_link_display.allow_tags = True
    share_link_display.short_description = "Lien de partage"

@admin.register(Advertisement)
class AdvertisementAdmin(admin.ModelAdmin):
    list_display = ("id", "enable", "created_at")
    list_filter = ("enable", "created_at")
    readonly_fields = ("id", "created_at")
    fieldsets = (
        (None, {"fields": ("id", "enable", "image")}),
        ("Metadata", {"fields": ("created_at",)}),
    )

admin.site.register(IDLink)
admin.site.register(Coupon)
admin.site.register(TestModel)
admin.site.register(RechargeMobcashBalance)
