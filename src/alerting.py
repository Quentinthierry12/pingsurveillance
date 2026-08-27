"""Traduit les changements d'état des services en appels téléphoniques,
avec réessais si tu ne décroches pas, et relance périodique si la panne dure.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone

from audio_utils import wav_duration as _wav_duration
from config import AppConfig, ServiceConfig
from sip_agent import SipAgent
from status_store import StatusStore
from tts import synthesize

logger = logging.getLogger("alerting")


class Alerting:
    def __init__(self, cfg: AppConfig, store: StatusStore, sip: SipAgent):
        self.cfg = cfg
        self.store = store
        self.sip = sip
        self._call_lock = threading.Lock()

    # -- point d'entrée branché sur Monitor.on_transition ---------------------

    def on_transition(self, service: ServiceConfig, is_down: bool, error: str) -> None:
        if is_down:
            text = (
                f"Alerte. Le service {service.name} est hors ligne. "
                f"Raison probable : {error}. Je vérifie et je te tiens au courant."
            )
        else:
            text = f"Bonne nouvelle. Le service {service.name} est de nouveau en ligne."
        threading.Thread(target=self._speak_and_call, args=(service.name, text), daemon=True).start()

    def recall_still_down_services(self) -> None:
        """À appeler périodiquement (ex: toutes les minutes) depuis main.py :
        relance un appel pour les services toujours down si le dernier appel
        remonte à plus de `recall_interval_minutes`.
        """
        now = datetime.now(timezone.utc)
        for state in self.store.all():
            if state.up:
                continue
            last_call = _parse(state.last_alert_call) or _parse(state.since)
            if last_call is None:
                continue
            elapsed_min = (now - last_call).total_seconds() / 60
            if elapsed_min >= self.cfg.recall_interval_minutes:
                text = (
                    f"Rappel. Le service {state.name} est toujours hors ligne "
                    f"depuis {_human_since(state.since)}."
                )
                threading.Thread(target=self._speak_and_call, args=(state.name, text), daemon=True).start()

    # -- mode test --------------------------------------------------------------

    def trigger_test_call(self) -> None:
        text = "Ceci est un appel de test. Si tu entends ce message, la chaîne d'alerte fonctionne correctement."
        self._speak_and_call("__test__", text)

    # -- interne ------------------------------------------------------------

    def _speak_and_call(self, service_name: str, text: str) -> None:
        with self._call_lock:
            try:
                wav_path = self.cfg.data_dir / "tmp" / f"alert_{int(time.time())}.wav"
                synthesize(text, wav_path, self.cfg.piper_voice, self.cfg.data_dir / "piper")
                duration = _wav_duration(wav_path)

                answered = False
                for attempt in range(1, self.cfg.call_retry_count + 1):
                    logger.info("Appel d'alerte (%s), tentative %d/%d", service_name, attempt, self.cfg.call_retry_count)
                    answered = self.sip.call_and_play(self.cfg.sip_alert_target, str(wav_path), duration)
                    if answered:
                        break
                    time.sleep(self.cfg.call_retry_delay_seconds)

                if service_name != "__test__":
                    self.store.update(service_name, last_alert_call=datetime.now(timezone.utc).isoformat())

                if not answered:
                    logger.error("Aucune réponse après %d tentatives pour %s", self.cfg.call_retry_count, service_name)

                wav_path.unlink(missing_ok=True)
            except Exception:
                logger.exception("Échec de la chaîne d'alerte pour %s", service_name)


def _parse(iso_ts: str):
    if not iso_ts:
        return None
    try:
        return datetime.fromisoformat(iso_ts)
    except Exception:
        return None


def _human_since(iso_ts: str) -> str:
    dt = _parse(iso_ts)
    if dt is None:
        return "un moment indéterminé"
    minutes = int((datetime.now(timezone.utc) - dt).total_seconds() // 60)
    if minutes < 60:
        return f"{minutes} minutes"
    return f"{minutes // 60} heures"
