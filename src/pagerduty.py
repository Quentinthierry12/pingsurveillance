"""Client minimal pour l'API Events v2 de PagerDuty (déclenche de vraies
alertes avec appel téléphonique, selon les règles de notification configurées
par l'utilisateur dans son compte PagerDuty).

Doc: https://developer.pagerduty.com/docs/events-api-v2/trigger-events/
"""
from __future__ import annotations

import logging

import httpx

logger = logging.getLogger("pagerduty")

ENQUEUE_URL = "https://events.pagerduty.com/v2/enqueue"


class PagerDutyClient:
    def __init__(self, routing_key: str):
        self.routing_key = routing_key

    def trigger(self, dedup_key: str, summary: str, severity: str = "critical", source: str = "pingsurveillance") -> None:
        self._send("trigger", dedup_key, summary=summary, severity=severity, source=source)

    def resolve(self, dedup_key: str, summary: str = "") -> None:
        self._send("resolve", dedup_key, summary=summary or "Résolu", severity="info", source="pingsurveillance")

    def _send(self, event_action: str, dedup_key: str, summary: str, severity: str, source: str) -> None:
        body = {
            "routing_key": self.routing_key,
            "event_action": event_action,
            "dedup_key": dedup_key,
            "payload": {
                "summary": summary,
                "severity": severity,
                "source": source,
            },
        }
        try:
            resp = httpx.post(ENQUEUE_URL, json=body, timeout=10.0)
            if resp.status_code >= 300:
                logger.error("PagerDuty a répondu %s: %s", resp.status_code, resp.text)
            else:
                logger.info("Événement PagerDuty '%s' envoyé pour '%s'", event_action, dedup_key)
        except httpx.RequestError as e:
            logger.error("Échec d'envoi de l'événement PagerDuty: %s", e)
