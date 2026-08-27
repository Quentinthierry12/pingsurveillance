"""Synthèse vocale locale (Piper) + traitement audio pour un rendu façon 'assistant IA'.

Piper seul ne sonne pas comme Jarvis : on applique en plus une petite chaîne
d'effets ffmpeg (léger filtrage + reverb courte + touche de modulation) pour
se rapprocher d'un timbre robotique/assistant. À ajuster à l'oreille une fois
déployé — c'est la partie la plus "goût personnel" du projet.
"""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger("tts")

# Chaîne de filtres ffmpeg appliquée après la synthèse Piper.
# - highpass/lowpass : resserre le spectre (effet "haut-parleur radio/casque")
# - aecho : léger écho métallique
# - equalizer : accentue un peu les médiums-aigus pour un rendu plus "synthétique"
JARVIS_FILTER_CHAIN = (
    "highpass=f=120,"
    "lowpass=f=7000,"
    "equalizer=f=3000:t=q:w=1:g=4,"
    "aecho=0.7:0.6:20:0.25"
)


def _ensure_voice(voice: str, data_dir: Path) -> None:
    """Télécharge le modèle de voix Piper s'il n'est pas déjà présent.

    Contrairement à ce que suggère la doc Piper généraliste, la CLI `piper`
    ne télécharge PAS automatiquement une voix manquante : il faut appeler
    `python -m piper.download_voices` explicitement au préalable.
    """
    data_dir.mkdir(parents=True, exist_ok=True)
    if any(data_dir.glob(f"{voice}.onnx")):
        return
    logger.info("Voix Piper '%s' absente, téléchargement...", voice)
    result = subprocess.run(
        ["python3", "-m", "piper.download_voices", voice, "--data-dir", str(data_dir)],
        capture_output=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Échec du téléchargement de la voix Piper '{voice}': {result.stderr.decode(errors='replace')}"
        )


def synthesize(text: str, out_path: Path, voice: str, data_dir: Path) -> Path:
    """Génère un wav à partir de texte via Piper, puis applique l'effet 'Jarvis'.

    Nécessite le binaire `piper` (paquet pip `piper-tts`) dans le PATH.
    """
    _ensure_voice(voice, data_dir)
    raw_path = out_path.with_suffix(".raw.wav")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    result = subprocess.run(
        ["piper", "--model", voice, "--data-dir", str(data_dir), "--output_file", str(raw_path)],
        input=text.encode("utf-8"),
        capture_output=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Échec Piper TTS: {result.stderr.decode(errors='replace')}")

    # Effet 'Jarvis' via ffmpeg. Si ffmpeg échoue pour une raison quelconque,
    # on retombe sur la voix brute plutôt que de bloquer toute la chaîne d'alerte.
    try:
        ff = subprocess.run(
            ["ffmpeg", "-y", "-i", str(raw_path), "-af", JARVIS_FILTER_CHAIN, str(out_path)],
            capture_output=True,
        )
        if ff.returncode != 0:
            logger.warning("ffmpeg a échoué, on garde la voix brute: %s", ff.stderr.decode(errors="replace"))
            raw_path.replace(out_path)
        else:
            raw_path.unlink(missing_ok=True)
    except FileNotFoundError:
        logger.warning("ffmpeg introuvable, on garde la voix brute Piper.")
        raw_path.replace(out_path)

    return out_path
