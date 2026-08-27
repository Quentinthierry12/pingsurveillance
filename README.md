# PingSurveillance

Surveille des URLs de services (typiquement déployés sur Coolify) et
déclenche une **vraie alerte téléphonique** via PagerDuty quand un service
tombe. Un **mode test** permet de déclencher une alerte sans attendre une
vraie panne, et l'état de tous les services est consultable via une API HTTP.

## Comment ça marche

- **Surveillance** ([src/monitor.py](src/monitor.py)) : ping HTTP périodique de chaque URL listée dans `config/services.yaml`, avec seuils anti-faux-positifs (X échecs consécutifs avant de déclarer "down").
- **Alertes** ([src/pagerduty.py](src/pagerduty.py), [src/alerting.py](src/alerting.py)) : envoie un événement à l'API Events v2 de PagerDuty à chaque changement d'état (panne / retour en ligne). C'est **PagerDuty qui t'appelle** ensuite, selon les règles de notification que tu configures sur ton compte (téléphone en priorité, avec escalade si tu ne réponds pas).
- **API HTTP** ([src/api.py](src/api.py)) : consultation du statut en JSON + endpoints de test.

## Pourquoi PagerDuty plutôt que Linphone/SIP ?

La première version de cet outil pilotait un softphone SIP (`linphonec`) en
ligne de commande pour appeler directement via un compte Linphone. Techniquement
faisable sur le papier, mais en déploiement réel sur ce serveur, `linphonec`
restait bloqué en état interne `LinphoneGlobalStartup` et l'enregistrement SIP
n'aboutissait jamais (`LinphoneRegistrationNone`), malgré plusieurs correctifs
(carte son factice, mode `soundcard use files`, etc.). Plutôt que de continuer
à déboguer un softphone headless sans garantie de résultat, on est passé sur
PagerDuty : gratuit jusqu'à 5 utilisateurs, appels téléphoniques fiables et
intégrés, infrastructure déjà éprouvée à grande échelle.

**Limite à connaître** : contrairement à l'idée initiale, tu ne peux pas
"appeler le bot" pour avoir le statut à la voix — PagerDuty ne fait que
t'appeler, pas l'inverse. Pour consulter le statut à la demande, utilise
l'endpoint `GET /status` (voir plus bas).

## Mise en place

### 1. Configure PagerDuty

1. Crée un compte sur [pagerduty.com](https://www.pagerduty.com/) (offre gratuite, jusqu'à 5 utilisateurs).
2. Crée un **Service** (Services → Service Directory → New Service).
3. Ajoute une intégration **Events API v2** à ce service, et récupère l'**Integration Key** (c'est ta `PAGERDUTY_ROUTING_KEY`).
4. Dans ton profil (Settings → My Profile → Notifications) : configure une règle du type "Appelle-moi immédiatement" pour les incidents urgents, avec ton numéro de téléphone vérifié.

### 2. Configure le projet

```bash
cp .env.example .env
cp config/services.example.yaml config/services.yaml
```

Remplis `.env` :
- `PAGERDUTY_ROUTING_KEY` : la clé d'intégration récupérée à l'étape 1.
- `API_KEY` : un secret de ton choix pour protéger l'API HTTP.

Édite `config/services.yaml` avec tes vraies URLs de services Coolify.

⚠️ **Sur Coolify, la config est bakée dans l'image Docker** (committée dans le repo Git), pas montée en volume — un bind mount sur `/app/config` écrase le contenu de l'image par un dossier vide côté serveur et fait planter le démarrage (vécu en prod). Donc : `git add config/services.yaml`, commit, push, puis redéploie sur Coolify à chaque changement de la liste des services. Pense aussi à mettre à jour `CONFIG_PATH` sur `/app/config/services.yaml` (au lieu de `services.example.yaml`) une fois ton vrai fichier en place.

### 3. Lance en local

```bash
pip install -r requirements.txt
python src/main.py
```

### 4. Déploie sur Coolify

1. Pousse ce dossier sur un repo Git (GitHub/GitLab/etc.) — Coolify déploie depuis un repo.
2. Dans Coolify : **New Resource → Docker Compose**, pointe vers ce repo (`docker-compose.yml` à la racine).
3. Renseigne les variables d'environnement du `.env.example` dans l'onglet "Environment Variables" de Coolify (ne commite jamais le `.env` réel).
4. Monte un volume persistant sur `/app/data` (déjà prévu dans `docker-compose.yml`) pour que l'état des services survive aux redéploiements.
5. Déploie. Regarde les logs pour confirmer `API HTTP sur le port 8085`.

## Mode test

Une fois lancé, l'API écoute sur `API_PORT` (8085 par défaut). Toutes les routes protégées attendent un header `X-API-Key: <ta clé>`.

```bash
# Alerte de test réelle (vérifie toute la chaîne : envoi PagerDuty + notification/appel),
# auto-résolue après 5s pour ne pas laisser un faux incident ouvert
curl -X POST http://localhost:8085/test/call -H "X-API-Key: $API_KEY"

# Simuler une panne d'un service précis (déclenche une vraie alerte PagerDuty)
curl -X POST "http://localhost:8085/test/simulate/API%20principale?state=down" -H "X-API-Key: $API_KEY"

# Simuler le retour en ligne
curl -X POST "http://localhost:8085/test/simulate/API%20principale?state=up" -H "X-API-Key: $API_KEY"

# Statut courant de tous les services
curl http://localhost:8085/status -H "X-API-Key: $API_KEY"

# Forcer un cycle de ping immédiat (sans simulation)
curl -X POST http://localhost:8085/test/check-now -H "X-API-Key: $API_KEY"
```

## Comportement des alertes

- Un service doit échouer `failure_threshold` fois **de suite** avant d'être déclaré "down" (évite d'alerter pour un simple hoquet réseau).
- À chaque changement d'état (down ou retour en ligne), un événement `trigger`/`resolve` est envoyé à PagerDuty avec une `dedup_key` par service, pour que les pannes/retours du même service soient bien reliés au même incident côté PagerDuty.
- Les relances/escalades (rappeler si tu ne réponds pas, etc.) sont gérées **par PagerDuty lui-même**, configurables dans tes règles de notification — pas besoin de les gérer ici.
- Tous les seuils sont dans `config/services.yaml`.
