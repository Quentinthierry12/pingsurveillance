"""Point d'entrée : câble monitor + agent SIP + alerting + écoute entrante + API."""
from __future__ import annotations

import logging
import threading
import time

import uvicorn

from alerting import Alerting
from api import create_app
from config import load_config
from inbound import InboundListener
from monitor import Monitor
from sip_agent import SipAgent
from status_store import StatusStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("main")


def recall_loop(alerting: Alerting, interval_seconds: int = 60) -> None:
    while True:
        time.sleep(interval_seconds)
        try:
            alerting.recall_still_down_services()
        except Exception:
            logger.exception("Erreur dans la boucle de relance")


def main() -> None:
    cfg = load_config()
    store = StatusStore(cfg.data_dir / "status.json")

    sip = SipAgent(cfg.sip_bot_username, cfg.sip_bot_password, cfg.sip_bot_domain)
    sip.start()

    alerting = Alerting(cfg, store, sip)
    monitor = Monitor(cfg, store, on_transition=alerting.on_transition)
    inbound = InboundListener(cfg, store, sip)

    threading.Thread(target=monitor.run_forever, daemon=True).start()
    threading.Thread(target=inbound.run_forever, daemon=True).start()
    threading.Thread(target=recall_loop, args=(alerting,), daemon=True).start()

    app = create_app(cfg, store, alerting, monitor)
    logger.info("API HTTP sur le port %d", cfg.api_port)
    uvicorn.run(app, host="0.0.0.0", port=cfg.api_port)


if __name__ == "__main__":
    main()
