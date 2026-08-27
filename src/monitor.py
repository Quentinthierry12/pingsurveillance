"""Boucle de ping des services + machine à états (up/down avec seuils anti-flap)."""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Callable

import httpx

from config import AppConfig, ServiceConfig
from status_store import StatusStore

logger = logging.getLogger("monitor")

# Appelé quand un service change d'état : (service_config, devient_down: bool, erreur: str)
AlertCallback = Callable[[ServiceConfig, bool, str], None]


class Monitor:
    def __init__(self, cfg: AppConfig, store: StatusStore, on_transition: AlertCallback):
        self.cfg = cfg
        self.store = store
        self.on_transition = on_transition
        self._stop = threading.Event()
        for s in cfg.services:
            self.store.ensure(s.name)

    def run_forever(self) -> None:
        logger.info(
            "Surveillance démarrée : %d service(s), intervalle %ds",
            len(self.cfg.services),
            self.cfg.check_interval_seconds,
        )
        while not self._stop.is_set():
            for service in self.cfg.services:
                self._check_one(service)
            self._stop.wait(self.cfg.check_interval_seconds)

    def stop(self) -> None:
        self._stop.set()

    def check_once_all(self) -> None:
        """Utilisé par le mode test / une route API pour forcer un cycle immédiat."""
        for service in self.cfg.services:
            self._check_one(service)

    def _check_one(self, service: ServiceConfig) -> None:
        ok, error = self._ping(service)
        state = self.store.ensure(service.name)
        now = _now()

        if ok:
            failures, successes = 0, state.consecutive_successes + 1
        else:
            failures, successes = state.consecutive_failures + 1, 0

        was_up = state.up
        becomes_down = was_up and not ok and failures >= self.cfg.failure_threshold
        becomes_up = (not was_up) and ok and successes >= self.cfg.recovery_threshold

        new_up = state.up
        since = state.since
        if becomes_down:
            new_up = False
            since = now
        elif becomes_up:
            new_up = True
            since = now

        self.store.update(
            service.name,
            up=new_up,
            consecutive_failures=failures,
            consecutive_successes=successes,
            since=since,
            last_check=now,
            last_error=error,
        )

        if becomes_down:
            logger.warning("%s est DOWN (%s)", service.name, error)
            self.on_transition(service, True, error)
        elif becomes_up:
            logger.info("%s est de nouveau UP", service.name)
            self.on_transition(service, False, error)
        elif not new_up:
            # Toujours down : le recall périodique est géré côté appelant (alerting.py)
            pass

    def _ping(self, service: ServiceConfig) -> tuple[bool, str]:
        try:
            with httpx.Client(timeout=service.timeout_seconds, follow_redirects=True) as client:
                resp = client.request(service.method, service.url)
            if resp.status_code == service.expected_status:
                return True, ""
            return False, f"HTTP {resp.status_code} (attendu {service.expected_status})"
        except httpx.TimeoutException:
            return False, "timeout"
        except httpx.RequestError as e:
            return False, f"erreur réseau: {e}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
