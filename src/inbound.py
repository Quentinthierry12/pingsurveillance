"""Écoute des appels ENTRANTS : quand tu appelles le bot, il décroche
automatiquement (autoanswer activé au démarrage) et te lit le statut courant
de tous les services surveillés.
"""
from __future__ import annotations

import logging
import threading
import time

from audio_utils import wav_duration as _wav_duration
from config import AppConfig
from sip_agent import SipAgent
from status_store import StatusStore
from tts import synthesize

logger = logging.getLogger("inbound")


class InboundListener:
    def __init__(self, cfg: AppConfig, store: StatusStore, sip: SipAgent):
        self.cfg = cfg
        self.store = store
        self.sip = sip
        self._stop = threading.Event()

    def run_forever(self, poll_interval: float = 1.5) -> None:
        logger.info("Écoute des appels entrants démarrée.")
        was_offhook = False
        while not self._stop.is_set():
            time.sleep(poll_interval)
            try:
                offhook = self.sip.is_offhook()
            except Exception:
                logger.exception("Erreur en interrogeant l'état de la ligne SIP")
                continue

            # Transition onhook -> offhook, et ce n'est PAS un appel sortant
            # déclenché par la partie alerting : c'est donc un appel entrant
            # que le module autoanswer de linphonec vient de décrocher.
            if offhook and not was_offhook and not self.sip.outbound_in_progress.is_set():
                self._handle_inbound()
            was_offhook = offhook

    def stop(self) -> None:
        self._stop.set()

    def _handle_inbound(self) -> None:
        logger.info("Appel entrant détecté -> lecture du statut vocal")
        try:
            text = "Bonjour. " + self.store.voice_report()
            wav_path = self.cfg.data_dir / "tmp" / f"status_{int(time.time())}.wav"
            synthesize(text, wav_path, self.cfg.piper_voice, self.cfg.data_dir / "piper")
            duration = _wav_duration(wav_path)

            # laisse l'audio de l'appel s'établir après le décroché automatique
            time.sleep(1.5)
            self.sip.play(str(wav_path))
            time.sleep(duration + 1.0)
            self.sip.hangup()
            wav_path.unlink(missing_ok=True)
        except Exception:
            logger.exception("Échec de la lecture du statut sur appel entrant")
