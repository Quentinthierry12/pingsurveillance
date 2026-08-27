"""API HTTP légère : consultation du statut + mode test (déclenchement d'appels
sans attendre une vraie panne)."""
from __future__ import annotations

import threading
from dataclasses import asdict

from fastapi import Depends, FastAPI, Header, HTTPException

from alerting import Alerting
from config import AppConfig
from monitor import Monitor
from status_store import StatusStore


def create_app(cfg: AppConfig, store: StatusStore, alerting: Alerting, monitor: Monitor) -> FastAPI:
    app = FastAPI(title="PingSurveillance", description="Surveillance de services + alertes vocales SIP")

    def check_api_key(x_api_key: str = Header(default="")) -> None:
        if not cfg.api_key or x_api_key != cfg.api_key:
            raise HTTPException(status_code=401, detail="Clé API invalide ou manquante (header X-API-Key)")

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.get("/status", dependencies=[Depends(check_api_key)])
    def status():
        return {"services": [asdict(s) for s in store.all()]}

    @app.post("/test/call", dependencies=[Depends(check_api_key)])
    def test_call():
        """Déclenche un appel de test réel (voix + décroché) sans lien avec une panne."""
        threading.Thread(target=alerting.trigger_test_call, daemon=True).start()
        return {"ok": True, "message": "Appel de test lancé, décroche pour vérifier le rendu vocal."}

    @app.post("/test/simulate/{service_name}", dependencies=[Depends(check_api_key)])
    def simulate(service_name: str, state: str):
        """Force artificiellement un service à down/up pour tester toute la
        chaîne (statut -> décision -> appel) sans attendre un vrai incident.
        `state` = "down" ou "up".
        """
        if state not in ("down", "up"):
            raise HTTPException(status_code=400, detail="state doit être 'down' ou 'up'")

        matching = next((s for s in cfg.services if s.name == service_name), None)
        if matching is None:
            raise HTTPException(status_code=404, detail=f"Service inconnu: {service_name}")

        is_down = state == "down"
        store.update(
            service_name,
            up=not is_down,
            consecutive_failures=cfg.failure_threshold if is_down else 0,
            consecutive_successes=0 if is_down else cfg.recovery_threshold,
        )
        alerting.on_transition(matching, is_down, "simulation via /test/simulate")
        return {"ok": True, "service": service_name, "state": state}

    @app.post("/test/check-now", dependencies=[Depends(check_api_key)])
    def check_now():
        """Force un cycle de ping immédiat sur tous les services (sans simulation)."""
        threading.Thread(target=monitor.check_once_all, daemon=True).start()
        return {"ok": True}

    return app
