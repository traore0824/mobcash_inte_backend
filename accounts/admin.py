from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _
from .models import AppName, User


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
        "date_joined",
        "last_login",
    )
    list_filter = ("is_active", "is_staff", "is_supperuser", "is_block", "is_delete")
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
                )
            },
        ),
        (_("Références"), {"fields": ("referrer_code", "referral_code")}),
        (
            _("Connexion"),
            {"fields": ("last_login", "date_joined", "otp", "otp_created_at")},
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


@admin.register(AppName)
class AppNameAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "enable",
        "city",
        "active_for_deposit",
        "active_for_with",
        "order",
    )
    list_filter = ("enable", "active_for_deposit", "active_for_with", "city")
    search_fields = ("name", "city", "street")
    ordering = ("order",)
    fieldsets = (
        ("Informations principales", {"fields": ("name", "image", "enable", "order")}),
        ("Localisation", {"fields": ("city", "street")}),
        ("Paramètres de caisse", {"fields": ("cashdeskid", "cashierpass", "hash")}),
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
