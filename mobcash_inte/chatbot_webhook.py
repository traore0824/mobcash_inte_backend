"""
Récepteur du webhook My Customer (event: human_reply) + polling mobile.

Flux :
  conseiller répond dans le dashboard My Customer
    → My Customer POST ici
    → on stocke ChatbotHumanMessage
    → le mobile récupère via GET /mobcash/v2/chatbot/human-messages/ (polling).
"""

from __future__ import annotations

import json
import logging

from django.db import IntegrityError
from rest_framework import permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from mobcash_inte.models import ChatbotHumanMessage

logger = logging.getLogger("mobcash_inte_backend.transactions")

EVENT_HUMAN_REPLY = "human_reply"


class ChatbotWebhookView(APIView):
    """POST My Customer → stocke la réponse humaine pour le polling mobile."""

    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    def post(self, request):
        try:
            body = json.loads(request.body.decode("utf-8"))
        except Exception:
            return Response({"detail": "JSON invalide."}, status=400)

        event = (body.get("event") or "").strip()
        data = body.get("data") or {}
        if event != EVENT_HUMAN_REPLY:
            return Response({"status": "ignored", "event": event})

        conversation_id = (data.get("conversation_id") or "").strip()
        content = (data.get("message") or "").strip()
        media_type = (data.get("media_type") or "text").strip().lower()
        media_url = (data.get("media_url") or "").strip()
        if media_type not in {"text", "audio", "image"}:
            media_type = "text"
        if not conversation_id or (not content and not media_url):
            return Response({"detail": "conversation_id et message requis."}, status=400)
        if not content:
            content = "Message vocal" if media_type == "audio" else "Image"

        customer = data.get("customer") or {}
        remote_id = (data.get("message_id") or "").strip() or None
        try:
            ChatbotHumanMessage.objects.create(
                conversation_id=conversation_id,
                remote_message_id=remote_id,
                customer_external_id=(customer.get("external_id") or "").strip(),
                content=content,
                media_type=media_type,
                media_url=media_url[:1000],
            )
        except IntegrityError:
            return Response({"status": "duplicate"})

        logger.info("Chatbot human_reply stocké — conversation=%s", conversation_id)
        return Response({"status": "ok"})


class ChatbotHumanMessagesView(APIView):
    """GET ?conversation_id=… [&after=ISO] → réponses humaines (polling mobile)."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        conversation_id = (request.GET.get("conversation_id") or "").strip()
        if not conversation_id:
            return Response({"detail": "conversation_id est requis."}, status=400)

        user = request.user
        allowed_ids = {
            str(getattr(user, "id", "") or ""),
            str(getattr(user, "email", "") or ""),
            str(getattr(user, "username", "") or ""),
        }
        allowed_ids.discard("")

        from datetime import timedelta

        from django.utils import timezone

        cutoff = timezone.now() - timedelta(hours=24)
        qs = ChatbotHumanMessage.objects.filter(
            conversation_id=conversation_id,
            created_at__gte=cutoff,
        )
        after = (request.GET.get("after") or "").strip()
        if after:
            from django.utils.dateparse import parse_datetime

            after_dt = parse_datetime(after)
            if after_dt is not None:
                qs = qs.filter(created_at__gt=after_dt)

        messages = []
        for msg in qs.order_by("created_at")[:100]:
            if msg.customer_external_id and msg.customer_external_id not in allowed_ids:
                continue
            messages.append(
                {
                    "id": str(msg.id),
                    "conversation_id": msg.conversation_id,
                    "content": msg.content,
                    "media_type": msg.media_type or "text",
                    "media_url": msg.media_url or "",
                    "created_at": msg.created_at.isoformat(),
                }
            )

        return Response({"messages": messages, "count": len(messages)})
