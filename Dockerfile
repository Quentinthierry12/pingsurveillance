FROM debian:bookworm-slim

# linphone-cli   -> linphonec / linphonecsh (moteur SIP piloté par script)
# ffmpeg         -> effet audio "Jarvis" appliqué sur la voix Piper
# alsa-utils     -> nécessaire pour configurer une carte son factice (pas de vrai
#                    micro/haut-parleur dans un conteneur serveur)
# python3-pip/venv, curl, ca-certificates -> runtime Python + téléchargement des voix Piper
RUN apt-get update && apt-get install -y --no-install-recommends \
    linphone-cli \
    ffmpeg \
    alsa-utils \
    python3 \
    python3-venv \
    python3-pip \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# --- Carte son factice (headless) ------------------------------------------
# ⚠️ NON VÉRIFIÉ EN CONDITIONS RÉELLES : linphonec attend une carte son ALSA
# pour la capture/lecture ; ce conteneur n'a ni micro ni haut-parleur. Ce
# fichier déclare un device "null" pour que linphonec démarre sans planter.
# Si l'enregistrement/appel échoue avec une erreur liée à la carte son une
# fois déployé, c'est le premier endroit à regarder (essaie
# `linphonecsh generic "soundcard list"` dans le conteneur pour voir les
# devices détectés, et ajuste ici).
RUN printf 'pcm.!default {\n  type null\n}\nctl.!default {\n  type null\n}\n' > /etc/asound.conf

RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:${PATH}"

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY config/services.example.yaml ./config/services.example.yaml

RUN mkdir -p /app/data

EXPOSE 8085

CMD ["python3", "src/main.py"]
