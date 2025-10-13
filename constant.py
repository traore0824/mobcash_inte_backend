from django.utils.translation import gettext_lazy as _

INVALID_EMAIL = _("Please enter a valid email address.")
PASSWORD_NOT_MATCH = _("The passwords do not match.")
PASSWORD_NOT_STRONG = _(
    "The password must include at least one uppercase letter, one lowercase letter, one digit, and be at least 6 characters long."
)


def MINIMUM_DEPOSIT_MESSAGE(MINIMUM_DEPOSIT):
    return _(f"Minumum deposit is {MINIMUM_DEPOSIT} F CFA")


def MINIMUM_WITHDRAWAL_MESSAGE(MINIMUM_WITHDRAWAL):
    return _(f"Minumum withdrawal is {MINIMUM_WITHDRAWAL} F CFA")


EMAIL_ALREADY_EXIST = _("A user with this email field already exists.")
PHONE_ALREADY_EXIST = _("A user with this phone field already exists.")
REQUIRED_FIELD = _("is required")
INVALID_OTP = _(
    "The verification code is incorrect or has expired. Please request a new code."
)
INVALID_EMAIL_PASSWORD = _("Email or password is incorrect.")
USER_DELETED_OR_BLOCKED = _("This account is deleted or blocked.")
MINIMUM_BET_AMOUNT = 90
MINIMUM_COAST = 1

MINIMUM_DEPOSIT = 2
MINIMUM_WITHDRAWAL = 1000
BONUS_PERCENT = 2
BONUS_PERCENT_MAX = 100
CODE_TIMEOUT = 502
CODE_EXEPTION = 500
CODE_SUCCESS = 200
COUNT_REQUEST = 100
