"""État courant de chaque service, consulté via l'API HTTP /status.
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


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
