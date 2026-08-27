"""Point d'entrée : câble monitor + alerting (PagerDuty) + API."""
from __future__ import annotations

import logging
import threading

import uvicorn

from alerting import Alerting
from api import create_app
from config import load_config
from monitor import Monitor
from pagerduty import PagerDutyClient
from status_store import StatusStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("main")


def main() -> None:
    cfg = load_config()
    store = StatusStore(cfg.data_dir / "status.json")

    pagerduty = PagerDutyClient(cfg.pagerduty_routing_key)
    alerting = Alerting(cfg, store, pagerduty)
    monitor = Monitor(cfg, store, on_transition=alerting.on_transition)

    threading.Thread(target=monitor.run_forever, daemon=True).start()

    app = create_app(cfg, store, alerting, monitor)
    logger.info("API HTTP sur le port %d", cfg.api_port)
    uvicorn.run(app, host="0.0.0.0", port=cfg.api_port)


if __name__ == "__main__":
    main()
