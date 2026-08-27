"""Petits utilitaires audio partagés entre alerting.py et inbound.py."""
from __future__ import annotations

import wave
from pathlib import Path


def wav_duration(path: Path) -> float:
    try:
        with wave.open(str(path), "rb") as w:
            return w.getnframes() / float(w.getframerate())
    except Exception:
        return 8.0  # estimation de secours si le fichier est illisible
