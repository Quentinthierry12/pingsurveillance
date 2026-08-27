# PingSurveillance

Surveille des URLs de services (typiquement déployés sur Coolify) et t'alerte
**par appel téléphonique SIP** (via Linphone) avec une voix de synthèse
façon "assistant IA" quand un service tombe. Tu peux aussi **appeler le bot**
pour qu'il te donne le statut de tout, et un **mode test** permet de
déclencher des appels sans attendre une vraie panne.

## Comment ça marche

- **Surveillance** ([src/monitor.py](src/monitor.py)) : ping HTTP périodique de chaque URL listée dans `config/services.yaml`, avec seuils anti-faux-positifs (X échecs consécutifs avant de déclarer "down").
- **Voix** ([src/tts.py](src/tts.py)) : synthèse vocale 100% locale et gratuite avec [Piper](https://github.com/OHF-Voice/piper1-gpl), puis un léger traitement audio (ffmpeg) pour un rendu plus "robotique/assistant".
- **Téléphonie** ([src/sip_agent.py](src/sip_agent.py)) : utilise `linphonec`/`linphonecsh` (paquet Debian `linphone-cli`), le moteur SIP de Linphone piloté par ligne de commande — pas besoin de l'appli graphique.
- **Deux identités SIP distinctes** :
  - un **compte "bot"** dédié (à créer), qui s'enregistre et passe/reçoit les appels automatisés ;
  - **ton compte Linphone existant** (celui avec les notifications sur ton iPhone), que le bot appelle en cas d'alerte, et depuis lequel tu appelles le bot pour avoir le statut.
- **API HTTP** ([src/api.py](src/api.py)) : consultation du statut en JSON + endpoints de test.

## ⚠️ Ce qui n'a pas pu être testé ici

Je n'ai ni compte SIP ni téléphone dans cet environnement de développement.
Le code est écrit selon la documentation officielle de `linphonec`/`linphonecsh`,
mais **deux points sont à valider une fois déployé** :

1. **La carte son "headless"** ([Dockerfile](Dockerfile)) : le conteneur n'a pas de vrai micro/haut-parleur. J'ai mis un device ALSA factice (`null`) pour que `linphonec` démarre sans planter, mais si l'appel/lecture audio échoue, regarde en premier `linphonecsh generic "soundcard list"` dans le conteneur.
2. **Les noms exacts des commandes `linphonec`** ([src/sip_agent.py](src/sip_agent.py)) : `call`, `terminate`, `answer`, `autoanswer`, `play` sont documentés, mais leur syntaxe précise peut varier selon la version du paquet. Lance `linphonecsh generic "help"` dans le conteneur pour vérifier, et ajuste `sip_agent.py` si besoin.

Le reste (ping, seuils, état, API, TTS, effets audio) est du code standard, testable dès maintenant sans matériel spécial.

## Mise en place

### 1. Crée un compte SIP pour le "bot"

Le plus simple : ouvre l'appli Linphone (ou https://subscribe.linphone.org) et crée un **second** compte gratuit `sip.linphone.org`, différent de celui déjà sur ton iPhone. C'est ce compte que le programme utilisera pour appeler et répondre.

### 2. Configure

```bash
cp .env.example .env
cp config/services.example.yaml config/services.yaml
```

Remplis `.env` :
- `SIP_BOT_USERNAME` / `SIP_BOT_PASSWORD` / `SIP_BOT_DOMAIN` : le compte créé à l'étape 1.
- `SIP_ALERT_TARGET` : ton adresse SIP existante, ex. `sip:tonpseudo@sip.linphone.org` (celle qui sonne sur ton iPhone).
- `API_KEY` : un secret de ton choix pour protéger l'API HTTP.

Édite `config/services.yaml` avec tes vraies URLs de services Coolify.

⚠️ **Sur Coolify, la config est bakée dans l'image Docker** (committée dans le repo Git), pas montée en volume — un bind mount sur `/app/config` écrase le contenu de l'image par un dossier vide côté serveur et fait planter le démarrage (vécu en prod). Donc : `git add config/services.yaml`, commit, push, puis redéploie sur Coolify à chaque changement de la liste des services.

### 3. Lance en local (test rapide sans Docker si tu as `linphone-cli` installé)

```bash
pip install -r requirements.txt
python src/main.py
```

### 4. Déploie sur Coolify

1. Pousse ce dossier sur un repo Git (GitHub/GitLab/etc.) — Coolify déploie depuis un repo.
2. Dans Coolify : **New Resource → Docker Compose**, pointe vers ce repo (`docker-compose.yml` à la racine).
3. Renseigne les variables d'environnement du `.env.example` dans l'onglet "Environment Variables" de Coolify (ne commite jamais le `.env` réel).
4. Monte un volume persistant sur `/app/data` (déjà prévu dans `docker-compose.yml`) pour que l'état des services et les voix Piper téléchargées survivent aux redéploiements.
5. Déploie. Regarde les logs pour confirmer `Agent SIP démarré et enregistré...`.

## Mode test

Une fois lancé, l'API écoute sur `API_PORT` (8085 par défaut). Toutes les routes protégées attendent un header `X-API-Key: <ta clé>`.

```bash
# Appel de test "à blanc" (vérifie toute la chaîne voix + décroché, sans lien avec une panne)
curl -X POST http://localhost:8085/test/call -H "X-API-Key: $API_KEY"

# Simuler une panne d'un service précis (déclenche un vrai appel d'alerte)
curl -X POST "http://localhost:8085/test/simulate/API%20principale?state=down" -H "X-API-Key: $API_KEY"

# Simuler le retour en ligne
curl -X POST "http://localhost:8085/test/simulate/API%20principale?state=up" -H "X-API-Key: $API_KEY"

# Statut courant de tous les services
curl http://localhost:8085/status -H "X-API-Key: $API_KEY"

# Forcer un cycle de ping immédiat (sans simulation)
curl -X POST http://localhost:8085/test/check-now -H "X-API-Key: $API_KEY"
```

## Comportement des alertes

- Un service doit échouer `failure_threshold` fois **de suite** avant d'être déclaré "down" (évite d'appeler pour un simple hoquet réseau).
- À chaque changement d'état (down ou retour en ligne), un appel est passé, avec `call_retry_count` tentatives si tu ne décroches pas.
- Si un service reste down, un rappel est passé toutes les `recall_interval_minutes` minutes tant que ce n'est pas résolu.
- Tous ces réglages sont dans `config/services.yaml`.

## Appeler pour avoir le statut

Appelle simplement l'adresse SIP du compte "bot" depuis ton Linphone iPhone : il décroche automatiquement et te lit l'état de tous les services surveillés, puis raccroche.

## Personnaliser la voix "Jarvis"

- Change `PIPER_VOICE` dans `.env` pour une autre voix Piper (liste : https://github.com/OHF-Voice/piper1-gpl/blob/main/VOICES.md).
- Ajuste la chaîne de filtres `JARVIS_FILTER_CHAIN` dans [src/tts.py](src/tts.py) (echo, filtrage, égalisation) — c'est la partie la plus "à l'oreille", pense à réécouter après chaque changement.
- Le texte des messages est dans [src/alerting.py](src/alerting.py) et [src/inbound.py](src/inbound.py).
