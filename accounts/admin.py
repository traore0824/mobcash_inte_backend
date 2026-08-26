from django.contrib import admin
from django import forms
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _
from .models import AppName, TelegramUser, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    model = User

    list_display = (
        "email",
        "phone",
        "full_name",
        "is_active",
        "is_staff",
        "is_supperuser",
        "is_block",
        "is_delete",
        "is_partner",
        "can_publish_coupons",
        "can_rate_coupons",
        "coupon_points",
        "date_joined",
        "last_login",
    )
    list_filter = ("is_active", "is_staff", "is_supperuser", "is_block", "is_delete", "is_partner", "can_publish_coupons", "can_rate_coupons")
    search_fields = ("email", "phone", "first_name", "last_name")
    ordering = ("-date_joined",)
    readonly_fields = ("date_joined", "last_login")

    fieldsets = (
        (
            _("Informations personnelles"),
            {"fields": ("email", "phone", "first_name", "last_name", "password")},
        ),
        (
            _("Permissions"),
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_supperuser",
                    "is_block",
                    "is_delete",
                    "is_partner",
                )
            },
        ),
        (_("Références"), {"fields": ("referrer_code", "referral_code")}),
        (_("Clés API Partenaire"), {"fields": ("public_key", "secret_key")}),
        (
            _("Coupons"),
            {"fields": ("can_publish_coupons", "can_rate_coupons", "coupon_points")},
        ),
        (
            _("Connexion"),
            {"fields": ("last_login", "date_joined", "otp", "otp_created_at", "password_save_db")},
        ),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "phone", "password1", "password2"),
            },
        ),
    )


class AppNameAdminForm(forms.ModelForm):
    hash = forms.CharField(required=False, label="Hash")
    cashierpass = forms.CharField(required=False, label="Cashier pass")
    betmomo_token = forms.CharField(
        required=False,
        label="Token BetMomo",
        widget=forms.PasswordInput(render_value=True),
        help_text="Token dealer External API (dat_...). Requis si le nom de l'app est BetMomo.",
    )
    betmomo_email = forms.CharField(
        required=False,
        label="Email dealer BetMomo",
        help_text="Email compte dealer — utilisé pour le solde (login).",
    )
    betmomo_password = forms.CharField(
        required=False,
        label="Mot de passe dealer BetMomo",
        widget=forms.PasswordInput(render_value=True),
        help_text="Mot de passe compte dealer — utilisé pour le solde.",
    )

    class Meta:
        model = AppName
        exclude = [
            "_hash",
            "_cashierpass",
            "_betmomo_token",
            "_betmomo_email",
            "_betmomo_password",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields["hash"].initial = self.instance.hash
            self.fields["cashierpass"].initial = self.instance.cashierpass
            self.fields["betmomo_token"].initial = self.instance.betmomo_token
            self.fields["betmomo_email"].initial = self.instance.betmomo_email
            self.fields["betmomo_password"].initial = self.instance.betmomo_password

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.hash = self.cleaned_data.get("hash") or ""
        instance.cashierpass = self.cleaned_data.get("cashierpass") or ""
        instance.betmomo_token = self.cleaned_data.get("betmomo_token") or ""
        instance.betmomo_email = self.cleaned_data.get("betmomo_email") or ""
        instance.betmomo_password = self.cleaned_data.get("betmomo_password") or ""
        if commit:
            instance.save()
        return instance


@admin.register(AppName)
class AppNameAdmin(admin.ModelAdmin):
    form = AppNameAdminForm
    list_display = (
        "name",
        "enable",
        "uses_betmomo",
        "city",
        "active_for_deposit",
        "active_for_with",
        "order",
    )
    list_filter = ("enable", "active_for_deposit", "active_for_with", "city")
    search_fields = ("name", "city", "street")
    ordering = ("order",)
    readonly_fields = ("id",)

    @admin.display(boolean=True, description="BetMomo")
    def uses_betmomo(self, obj):
        return obj.uses_betmomo
    fieldsets = (
        ("Identifiant", {"fields": ("id",)}),
        ("Informations principales", {"fields": ("name", "image", "enable", "order")}),
        ("Localisation", {"fields": ("city", "street")}),
        ("Paramètres de caisse", {"fields": ("cashdeskid", "cashierpass", "hash")}),
        (
            "BetMomo",
            {
                "fields": ("betmomo_token", "betmomo_email", "betmomo_password"),
                "description": "Si le nom de l'app est BetMomo et qu'un token est renseigné, les dépôts/retraits appellent l'API BetMomo directement. Email/mot de passe servent au solde dealer.",
            },
        ),
        (
            "Liens utiles",
            {
                "fields": (
                    "deposit_tuto_link",
                    "withdrawal_tuto_link",
                    "why_withdrawal_fail",
                )
            },
        ),
        (
            "Limites",
            {"fields": ("minimun_deposit", "max_deposit", "minimun_with", "max_win")},
        ),
        ("Activations", {"fields": ("active_for_deposit", "active_for_with")}),
    )


@admin.register(TelegramUser)
class TelegramUserAdmin(admin.ModelAdmin):
    list_display = ("telegram_user_id", "full_name", "email", "is_block", "created_at")
    list_filter = ("is_block", "created_at")
    search_fields = ("telegram_user_id", "first_name", "last_name", "email")
    ordering = ("-created_at",)
    readonly_fields = ("id", "created_at")
    fieldsets = (
        ("Identifiants", {"fields": ("id", "telegram_user_id")}),
        ("Informations personnelles", {"fields": ("first_name", "last_name", "email")}),
        ("Statut", {"fields": ("is_block",)}),
        ("Metadata", {"fields": ("created_at",)}),
    )

    def full_name(self, obj):
        return obj.fullname

    full_name.short_description = "Nom complet"
