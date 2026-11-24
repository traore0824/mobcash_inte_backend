"""
Annulation paris Connect → Mobcash → app Mobcash Cancel.

POST  /api/v1/connect/betting-cancel/          (HMAC Connect)
GET   /api/v1/device/cancel-jobs/next/         (Bearer JWT admin is_staff, ou device token)
POST  /api/v1/device/cancel-jobs/<uuid>/result/ (Bearer JWT admin is_staff, ou device token)
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
from decimal import Decimal, InvalidOperation

import requests
from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken

from mobcash_inte.models import BettingCancelJob

logger = logging.getLogger("mobcash_inte")

_MAX_SKEW = 300


def _inbound_key() -> str:
    return (
        os.getenv("CONNECT_INBOUND_API_KEY")
        or os.getenv("MOBCASHAPI_API_KEY")
        or ""
    ).strip()


def _inbound_secret() -> str:
    return (
        os.getenv("CONNECT_INBOUND_API_SECRET")
        or os.getenv("MOBCASHAPI_API_SECRET")
        or ""
    ).strip()


def _device_token() -> str:
    return (os.getenv("MOBCASH_CANCEL_DEVICE_TOKEN") or "").strip()


def _connect_webhook_secret() -> str:
    return (
        os.getenv("CONNECT_CANCEL_WEBHOOK_SECRET")
        or os.getenv("CONNECT_INBOUND_API_SECRET")
        or os.getenv("MOBCASHAPI_API_SECRET")
        or ""
    ).strip()


def verify_connect_hmac(request) -> tuple[bool, str]:
    """Même schéma que Connect MobCashExternalService: timestamp+METHOD+path+body."""
    api_key = (request.headers.get("X-API-Key") or "").strip()
    ts_raw = (request.headers.get("X-Timestamp") or "").strip()
    sig = (request.headers.get("X-Signature") or "").strip().lower()
    expected_key = _inbound_key()
    secret = _inbound_secret()
    if not expected_key or not secret:
        return False, "CONNECT_INBOUND credentials missing"
    if not api_key or not ts_raw or not sig:
        return False, "missing auth headers"
    if not hmac.compare_digest(api_key, expected_key):
        return False, "bad api key"
    try:
        ts = int(ts_raw)
    except ValueError:
        return False, "bad timestamp"
    if abs(int(time.time()) - ts) > _MAX_SKEW:
        return False, "timestamp skew"
    path = request.path
    raw = request.body or b""
    if isinstance(raw, str):
        raw = raw.encode("utf-8")
    body = raw.decode("utf-8")
    message = f"{ts}{request.method.upper()}{path}{body}"
    expected = hmac.new(secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        return False, "bad signature"
    return True, "ok"


def verify_device_token(request) -> bool:
    token = _device_token()
    if not token:
        return False
    auth = (request.headers.get("Authorization") or "").strip()
    if auth.lower().startswith("bearer "):
        provided = auth[7:].strip()
    else:
        provided = (request.headers.get("X-Device-Token") or "").strip()
    return bool(provided) and hmac.compare_digest(provided, token)


def _staff_from_jwt(request):
    """Admin Mobcash (is_staff) connecté dans l'app via /auth/login (JWT)."""
    try:
        res = JWTAuthentication().authenticate(request)
    except (InvalidToken, AuthenticationFailed):
        return None
    if not res:
        return None
    user = res[0]
    if not user or not user.is_active or not user.is_staff:
        return None
    if getattr(user, "is_block", False) or getattr(user, "is_delete", False):
        return None
    return user


def authorize_device(request) -> tuple[bool, dict]:
    """JWT admin Mobcash, sinon device token legacy (env MOBCASH_CANCEL_DEVICE_TOKEN)."""
    user = _staff_from_jwt(request)
    if user is not None:
        return True, {
            "admin_id": str(user.pk),
            "admin_email": getattr(user, "email", "") or "",
        }
    if verify_device_token(request):
        return True, {"admin_id": "", "admin_email": "device_token"}
    return False, {}


def _notify_connect(job: BettingCancelJob) -> None:
    """Rappelle Connect avec le résultat final."""
    url = (job.callback_url or "").strip()
    if not url:
        base = (os.getenv("CONNECT_PRO_BASE_URL") or "").rstrip("/")
        if base:
            url = f"{base}/api/payments/webhooks/mobcash-cancel/"
    if not url:
        logger.warning("[BETTING_CANCEL] pas de callback_url pour job %s", job.id)
        return

    secret = _connect_webhook_secret()
    body = {
        "event": "cancellation.result",
        "requestId": str(job.id),
        "connectTransactionUid": job.connect_transaction_uid,
        "reference": job.reference,
        "userBetId": job.user_bet_id,
        "status": "CANCELLED" if job.status == "success" else "REJECTED",
        "outcome": "cancelled_final" if job.status == "success" else "rejected_final",
        "message": job.result_message or ("Transaction canceled" if job.status == "success" else "Cancel failed"),
        "platform": job.platform,
        "amount": str(job.amount) if job.amount is not None else None,
    }
    raw = json.dumps(body, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ts = int(time.time())
    headers = {
        "Content-Type": "application/json",
        "X-Request-ID": str(job.id),
        "X-Mobcash-Timestamp": str(ts),
    }
    if secret:
        sig = hmac.new(
            secret.encode("utf-8"),
            f"{ts}.".encode("utf-8") + raw,
            hashlib.sha256,
        ).hexdigest()
        headers["X-Mobcash-Signature"] = sig

    try:
        resp = requests.post(url, data=raw, headers=headers, timeout=30)
        logger.info(
            "[BETTING_CANCEL] callback Connect | job=%s | status=%s | http=%s",
            job.id,
            job.status,
            resp.status_code,
        )
    except Exception as e:
        logger.error("[BETTING_CANCEL] callback failed | job=%s | err=%s", job.id, e)


class ConnectBettingCancelView(APIView):
    """Connect crée un job d'annulation (async → app device)."""

    authentication_classes = []
    permission_classes = []

    def post(self, request, *args, **kwargs):
        ok, reason = verify_connect_hmac(request)
        if not ok:
            logger.warning("[BETTING_CANCEL] auth rejected | %s", reason)
            return Response(
                {"success": False, "error": "UNAUTHORIZED", "message": reason},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        data = request.data if isinstance(request.data, dict) else {}
        user_bet_id = str(
            data.get("user_bet_id") or data.get("userBetId") or data.get("player_user_id") or ""
        ).strip()
        reference = str(data.get("reference") or "").strip()
        if not user_bet_id or not reference:
            return Response(
                {"success": False, "error": "MISSING_FIELDS", "message": "user_bet_id et reference requis"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        amount = None
        raw_amount = data.get("amount")
        if raw_amount is not None and str(raw_amount).strip() != "":
            try:
                amount = Decimal(str(raw_amount))
            except (InvalidOperation, ValueError):
                amount = None

        existing = BettingCancelJob.objects.filter(
            reference=reference,
            status__in=["pending", "processing", "success"],
        ).order_by("-created_at").first()
        if existing and existing.status == "success":
            return Response(
                {
                    "success": True,
                    "status": "CANCELLED",
                    "outcome": "cancelled_final",
                    "request_id": str(existing.id),
                    "message": existing.result_message or "Already cancelled",
                }
            )
        if existing:
            # Déjà en file / en cours : pas de 2e job (sinon 2e annulation sur le téléphone)
            return Response(
                {
                    "success": True,
                    "status": "RECEIVED",
                    "outcome": "pending",
                    "request_id": str(existing.id),
                    "id": str(existing.id),
                    "message": "Cancellation already queued for device",
                }
            )

        job = BettingCancelJob.objects.create(
            user_bet_id=user_bet_id,
            reference=reference,
            connect_transaction_uid=str(
                data.get("connect_transaction_uid")
                or data.get("external_transaction_id")
                or data.get("transaction_uid")
                or ""
            ).strip(),
            platform=str(data.get("platform") or data.get("platform_name") or "").strip(),
            amount=amount,
            transaction_type=str(data.get("transaction_type") or "DEPOSIT").upper(),
            reason=str(data.get("reason") or "").strip(),
            callback_url=str(data.get("callback_url") or "").strip(),
            status="pending",
            raw_request=data,
        )

        logger.info(
            "[BETTING_CANCEL] job créé | id=%s | ref=%s | user=%s",
            job.id,
            job.reference,
            job.user_bet_id,
        )

        return Response(
            {
                "success": True,
                "status": "RECEIVED",
                "outcome": "pending",
                "request_id": str(job.id),
                "id": str(job.id),
                "message": "Cancellation queued for device",
            },
            # 200 (pas 202) : Connect MobCashExternalService._make_request n'accepte que 200/201
            status=status.HTTP_200_OK,
        )


class DeviceCancelJobNextView(APIView):
    """L'app récupère le prochain job pending."""

    authentication_classes = []
    permission_classes = []

    def get(self, request, *args, **kwargs):
        ok, actor = authorize_device(request)
        if not ok:
            return Response({"error": "UNAUTHORIZED"}, status=status.HTTP_401_UNAUTHORIZED)

        with transaction.atomic():
            job = (
                BettingCancelJob.objects.select_for_update(skip_locked=True)
                .filter(status="pending")
                .order_by("created_at")
                .first()
            )
            if not job:
                return Response({"job": None})
            job.status = "processing"
            job.claimed_at = timezone.now()
            job.raw_result = {**(job.raw_result or {}), "claimed_by": actor}
            job.save(update_fields=["status", "claimed_at", "raw_result", "updated_at"])

        logger.info(
            "[BETTING_CANCEL] job pris | id=%s | ref=%s | par=%s",
            job.id,
            job.reference,
            actor.get("admin_email") or actor.get("admin_id"),
        )

        return Response(
            {
                "job": {
                    "id": str(job.id),
                    "user_bet_id": job.user_bet_id,
                    "reference": job.reference,
                    "connect_transaction_uid": job.connect_transaction_uid,
                    "platform": job.platform,
                    "amount": str(job.amount) if job.amount is not None else None,
                    "transaction_type": job.transaction_type,
                    "reason": job.reason,
                }
            }
        )


class DeviceCancelJobResultView(APIView):
    """L'app reporte le résultat d'annulation."""

    authentication_classes = []
    permission_classes = []

    def post(self, request, uid, *args, **kwargs):
        ok, actor = authorize_device(request)
        if not ok:
            return Response({"error": "UNAUTHORIZED"}, status=status.HTTP_401_UNAUTHORIZED)

        job = BettingCancelJob.objects.filter(id=uid).first()
        if not job:
            return Response({"error": "NOT_FOUND"}, status=status.HTTP_404_NOT_FOUND)

        data = request.data if isinstance(request.data, dict) else {}
        success = bool(data.get("success"))
        message = str(data.get("message") or "").strip()

        if job.status in ("success", "failed"):
            return Response(
                {"success": True, "status": job.status, "message": "already finalized"}
            )

        job.status = "success" if success else "failed"
        job.result_message = message or ("Transaction canceled" if success else "Cancel failed")
        job.raw_result = {
            **(job.raw_result or {}),
            **data,
            "finished_by": actor,
        }
        job.finished_at = timezone.now()
        job.save()

        _notify_connect(job)

        return Response(
            {
                "success": True,
                "status": job.status,
                "request_id": str(job.id),
            }
        )
