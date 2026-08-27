"""Agent SIP basé sur linphonec/linphonecsh (paquet Debian `linphone-cli`).

linphonecsh pilote un daemon linphonec via un pipe : on peut l'enregistrer sur
un compte SIP, lui faire composer un numéro, lire un fichier wav pendant un
appel, raccrocher, et interroger son état (enregistré ? décroché ?).

⚠️ Cette couche n'a pas pu être testée avec un vrai compte SIP dans cet
environnement (pas d'accès réseau/téléphone). La logique de commandes suit
la documentation officielle de linphonec/linphonecsh ; si une commande a un
nom légèrement différent selon la version installée, lance
`linphonecsh generic "help"` en conteneur pour lister les commandes exactes
et ajuste GENERIC_* ci-dessous.
"""
from __future__ import annotations

import logging
import subprocess
import threading
import time

logger = logging.getLogger("sip_agent")

CMD = "linphonecsh"


class SipAgent:
    def __init__(self, username: str, password: str, domain: str):
        self.username = username
        self.password = password
        self.domain = domain
        self._ready = False
        # Mis à True pendant qu'un appel SORTANT (alerte) est en cours, pour que
        # l'écouteur d'appels entrants ne confonde pas cet appel avec un appel
        # entrant à qui répondre par le statut vocal.
        self.outbound_in_progress = threading.Event()

    # -- gestion du daemon -------------------------------------------------

    def start(self, daemon_ready_timeout: float = 20.0) -> None:
        """Démarre le daemon linphonec et s'enregistre sur le compte SIP du bot."""
        self._run(["init"])
        self._wait_daemon_ready(daemon_ready_timeout)
        self._run(
            [
                "register",
                "--username",
                self.username,
                "--host",
                self.domain,
                "--password",
                self.password,
            ],
            redact_from=6,  # masque la valeur du mot de passe (dernier élément) dans les logs/erreurs
        )
        # Autoréponse activée : indispensable pour le mode "j'appelle et j'ai le statut".
        self.generic("autoanswer enable")
        self._ready = True
        logger.info("Agent SIP démarré et enregistré en tant que %s@%s", self.username, self.domain)
        try:
            logger.info("Cartes son détectées: %s", self.generic("soundcard list").strip())
        except Exception as e:
            logger.warning("Impossible de lister les cartes son: %s", e)
        try:
            logger.info("Aide linphonec complète:\n%s", self.generic("help").strip())
        except Exception as e:
            logger.warning("Impossible de récupérer l'aide: %s", e)

    def _wait_daemon_ready(self, timeout: float) -> None:
        """Attend que le pipe vers le daemon linphonec soit disponible, au lieu
        d'un sleep fixe qui masquerait un vrai échec de démarrage du daemon."""
        deadline = time.time() + timeout
        last_error = ""
        while time.time() < deadline:
            proc = subprocess.run([CMD, "generic", "help"], capture_output=True, text=True)
            if proc.returncode == 0:
                return
            last_error = proc.stderr or proc.stdout
            time.sleep(0.5)
        raise RuntimeError(
            f"Le daemon linphonec n'a pas répondu dans les {timeout:.0f}s après 'linphonecsh init'. "
            f"Dernière erreur: {last_error}"
        )

    def stop(self) -> None:
        try:
            self._run(["exit"])
        except Exception:
            logger.exception("Erreur à l'arrêt du daemon SIP (ignorée)")

    def is_registered(self) -> bool:
        out = self._run(["status", "register"], check=False)
        return "registered" in out.lower() and "unregistered" not in out.lower()

    def is_offhook(self) -> bool:
        out = self._run(["status", "hook"], check=False)
        return "offhook" in out.lower()

    # -- actions d'appel -----------------------------------------------------

    def call(self, target_uri: str) -> str:
        return self._run(["dial", target_uri])

    def hangup(self) -> None:
        self.generic("terminate")

    def play(self, wav_path: str) -> None:
        self.generic(f"play {wav_path}")

    def generic(self, linphonec_command: str) -> str:
        return self._run(["generic", linphonec_command])

    # -- appel + lecture d'un message, avec attente ---------------------------

    def call_and_play(self, target_uri: str, wav_path: str, wav_duration_seconds: float, ring_timeout: float = 25.0) -> bool:
        """Appelle `target_uri`, attend le décroché, joue `wav_path`, raccroche.

        Retourne True si l'appel a été décroché et le message joué, False sinon
        (pas de réponse dans `ring_timeout` secondes).
        """
        self.outbound_in_progress.set()
        try:
            logger.info("État d'enregistrement avant appel: registered=%s", self.is_registered())
            dial_output = self.call(target_uri)
            logger.info("Résultat de 'dial %s': %s", target_uri, dial_output.strip())
            waited = 0.0
            interval = 1.0
            answered = False
            while waited < ring_timeout:
                time.sleep(interval)
                waited += interval
                if self.is_offhook():
                    answered = True
                    break

            if not answered:
                try:
                    calls_state = self.generic("calls")
                except Exception as e:
                    calls_state = f"(diagnostic indisponible: {e})"
                logger.warning(
                    "Pas de réponse à l'appel vers %s après %.0fs. État des appels: %s",
                    target_uri, ring_timeout, calls_state.strip() if isinstance(calls_state, str) else calls_state,
                )
                self.hangup()
                return False

            # petite pause pour laisser l'audio s'établir avant de lancer la lecture
            time.sleep(1.5)
            self.play(wav_path)
            time.sleep(wav_duration_seconds + 1.0)
            self.hangup()
            return True
        finally:
            self.outbound_in_progress.clear()

    # -- interne --------------------------------------------------------------

    def _run(self, args: list[str], check: bool = True, redact_from: int | None = None) -> str:
        proc = subprocess.run([CMD, *args], capture_output=True, text=True)
        if check and proc.returncode != 0:
            display_args = list(args)
            if redact_from is not None:
                display_args[redact_from:] = ["***"] * len(display_args[redact_from:])
            raise RuntimeError(f"linphonecsh {' '.join(display_args)} a échoué: {proc.stderr or proc.stdout}")
        return proc.stdout
