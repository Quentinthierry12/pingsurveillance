"""Chargement de la configuration : variables d'environnement + services.yaml."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()


@dataclass
class ServiceConfig:
    name: str
    url: str
    method: str = "GET"
    expected_status: int = 200
    timeout_seconds: float = 5.0


@dataclass
class AppConfig:
    # Surveillance
    check_interval_seconds: int = 30
    failure_threshold: int = 3
    recovery_threshold: int = 2
    recall_interval_minutes: int = 15
    services: list[ServiceConfig] = field(default_factory=list)

    # PagerDuty (déclenche les appels/notifications selon les règles de
    # l'utilisateur configurées dans son compte PagerDuty)
    pagerduty_routing_key: str = ""

    # API
    api_port: int = 8085
    api_key: str = ""

    # Chemins
    data_dir: Path = Path("./data")
    config_path: Path = Path("./config/services.yaml")


def load_config() -> AppConfig:
    config_path = Path(os.environ.get("CONFIG_PATH", "./config/services.yaml"))
    if not config_path.exists():
        raise FileNotFoundError(
            f"Fichier de config introuvable: {config_path}. "
            f"Copie config/services.example.yaml vers ce chemin et adapte-le."
        )

    with open(config_path, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    services = [
        ServiceConfig(
            name=s["name"],
            url=s["url"],
            method=s.get("method", "GET"),
            expected_status=s.get("expected_status", 200),
            timeout_seconds=float(s.get("timeout_seconds", 5.0)),
        )
        for s in raw.get("services", [])
    ]

    if not services:
        raise ValueError("Aucun service défini dans services.yaml — ajoute au moins une entrée.")

    cfg = AppConfig(
        check_interval_seconds=int(raw.get("check_interval_seconds", 30)),
        failure_threshold=int(raw.get("failure_threshold", 3)),
        recovery_threshold=int(raw.get("recovery_threshold", 2)),
        recall_interval_minutes=int(raw.get("recall_interval_minutes", 15)),
        services=services,
        pagerduty_routing_key=os.environ.get("PAGERDUTY_ROUTING_KEY", ""),
        api_port=int(os.environ.get("API_PORT", "8085")),
        api_key=os.environ.get("API_KEY", ""),
        data_dir=Path(os.environ.get("DATA_DIR", "./data")),
        config_path=config_path,
    )

    cfg.data_dir.mkdir(parents=True, exist_ok=True)

    missing = []
    if not cfg.pagerduty_routing_key:
        missing.append("PAGERDUTY_ROUTING_KEY")
    if not cfg.api_key:
        missing.append("API_KEY")
    if missing:
        raise ValueError(
            "Variables d'environnement manquantes dans .env : " + ", ".join(missing)
        )

    return cfg
