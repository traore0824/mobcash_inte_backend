from django.core.mail import EmailMessage
from django.template.defaultfilters import random
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.core.mail import BadHeaderError
from smtplib import SMTPException
import logging
from django.conf import settings
import string, secrets, random, re
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from logger import LoggerService
from rest_framework.pagination import PageNumberPagination
from .models import User

logger = logging.getLogger(__name__)


def create_otp(length=4):
    digits = string.digits
    otp = "".join(secrets.choice(digits) for _ in range(length))
    return otp


def validate_password(password: str):
    if not re.search(r"[0-9]", password):
        return False
    if not re.search(r"[a-z]", password):
        return False
    if not re.search(r"[A-Z]", password):
        return False
    if len(password) < 6:   
        return False
    return True


def send_mails(subject, to_email, template_name, context={}, body=None):
    try:
        user = User.objects.filter(email=to_email).first()
        context["user"] = user
        template = render_to_string(template_name, context)
        msg = EmailMultiAlternatives(
            subject=subject,
            body=body,
            from_email=settings.EMAIL_HOST_USER,
            to=[to_email],
        )
        msg.attach_alternative(template, "text/html")
        response = msg.send()
        return response
    except Exception as e:
        LoggerService.e(f"Erreur lors de l'envoi de l'email: {str(e)}")
        return str(e)


class CustomPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 25
    page_query_param = "page"
