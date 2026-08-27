"""État courant de chaque service, partagé entre le monitor et l'agent SIP
(pour répondre aux appels entrants "donne-moi le statut").
Persisté sur disque en JSON pour survivre à un redémarrage du conteneur.
"""
from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class ServiceState:
    name: str
    up: bool = True
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    since: str = ""  # timestamp ISO du dernier changement d'état
    last_check: str = ""
    last_error: str = ""
    last_alert_call: str = ""  # timestamp du dernier appel d'alerte envoyé pour cet incident


class StatusStore:
    def __init__(self, path: Path):
        self._path = path
        self._lock = threading.Lock()
        self._state: dict[str, ServiceState] = {}
        self._load()

    def _load(self) -> None:
        if self._path.exists():
            try:
                raw = json.loads(self._path.read_text(encoding="utf-8"))
                self._state = {k: ServiceState(**v) for k, v in raw.items()}
            except Exception:
                self._state = {}

    def _save(self) -> None:
        self._path.write_text(
            json.dumps({k: asdict(v) for k, v in self._state.items()}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def ensure(self, name: str) -> ServiceState:
        with self._lock:
            if name not in self._state:
                self._state[name] = ServiceState(name=name, since=_now())
                self._save()
            return self._state[name]

    def get(self, name: str) -> ServiceState | None:
        with self._lock:
            return self._state.get(name)

    def all(self) -> list[ServiceState]:
        with self._lock:
            return list(self._state.values())

    def update(self, name: str, **kwargs) -> ServiceState:
        with self._lock:
            st = self._state.setdefault(name, ServiceState(name=name, since=_now()))
            for k, v in kwargs.items():
                setattr(st, k, v)
            self._save()
            return st

    def voice_report(self) -> str:
        """Construit le texte (FR) lu au téléphone quand on appelle pour le statut."""
        services = self.all()
        if not services:
            return "Aucun service n'est actuellement surveillé."

        down = [s for s in services if not s.up]
        if not down:
            n = len(services)
            return f"Tous les systèmes sont opérationnels. Les {n} services surveillés répondent normalement."

        parts = [f"{len(down)} service{'s' if len(down) > 1 else ''} en panne."]
        for s in down:
            parts.append(f"{s.name}, hors ligne depuis {_human_since(s.since)}.")
        up_count = len(services) - len(down)
        if up_count:
            parts.append(f"Les {up_count} autres services fonctionnent normalement.")
        return " ".join(parts)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _human_since(iso_ts: str) -> str:
    try:
        dt = datetime.fromisoformat(iso_ts)
    except Exception:
        return "un moment indéterminé"
    delta = datetime.now(timezone.utc) - dt
    minutes = int(delta.total_seconds() // 60)
    if minutes < 1:
        return "moins d'une minute"
    if minutes < 60:
        return f"{minutes} minute{'s' if minutes > 1 else ''}"
    hours = minutes // 60
    return f"{hours} heure{'s' if hours > 1 else ''}"
