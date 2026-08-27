"""Traduit les changements d'état des services en alertes PagerDuty (qui se
charge elle-même d'appeler l'utilisateur selon ses règles de notification)."""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone

from config import AppConfig, ServiceConfig
from pagerduty import PagerDutyClient
from status_store import StatusStore

logger = logging.getLogger("alerting")


class Alerting:
    def __init__(self, cfg: AppConfig, store: StatusStore, pagerduty: PagerDutyClient):
        self.cfg = cfg
        self.store = store
        self.pagerduty = pagerduty

    # -- point d'entrée branché sur Monitor.on_transition ---------------------

    def on_transition(self, service: ServiceConfig, is_down: bool, error: str) -> None:
        dedup_key = f"pingsurveillance:{service.name}"
        if is_down:
            summary = f"{service.name} est hors ligne ({error})"
            threading.Thread(
                target=self.pagerduty.trigger, args=(dedup_key, summary), daemon=True
            ).start()
        else:
            summary = f"{service.name} est de nouveau en ligne"
            threading.Thread(
                target=self.pagerduty.resolve, args=(dedup_key, summary), daemon=True
            ).start()
        if service.name != "__test__":
            self.store.update(service.name, last_alert_call=datetime.now(timezone.utc).isoformat())

    def recall_still_down_services(self) -> None:
        """PagerDuty gère lui-même les escalades/relances selon les règles de
        notification de l'utilisateur ; pas besoin de relancer nous-mêmes.
        Gardé comme point d'extension si besoin plus tard."""
        return

    # -- mode test --------------------------------------------------------------

    def trigger_test_call(self) -> None:
        dedup_key = "pingsurveillance:__test__"
        self.pagerduty.trigger(
            dedup_key,
            "Ceci est une alerte de test PingSurveillance. Si tu la reçois, la chaîne fonctionne.",
        )
        # Auto-résolution après le test pour ne pas laisser un incident de test ouvert.
        threading.Timer(5.0, self.pagerduty.resolve, args=(dedup_key, "Fin du test")).start()
