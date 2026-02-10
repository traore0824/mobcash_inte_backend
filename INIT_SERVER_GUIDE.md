# Guide d'utilisation du script d'initialisation serveur

## 📋 Description

Ce script `init_server.sh` configure automatiquement votre application Django **directement sur le serveur sans Docker**. Il installe et configure tous les services nécessaires.

## ✨ Fonctionnalités

Le script effectue automatiquement :

### 1. **Détection de Python**
- ✅ Utilise la version Python déjà installée sur le système
- ✅ Installe Python 3 si absent
- ✅ Vérifie que la version est compatible (3.8+)

### 2. **Installation automatique des dépendances**
- ✅ PostgreSQL (base de données)
- ✅ Redis (cache et broker Celery)
- ✅ Nginx (serveur web)
- ✅ Certbot (certificats SSL Let's Encrypt)
- ✅ Supervisor (gestion de Celery)

### 3. **Configuration de la base de données**
- ✅ Création de la base de données PostgreSQL
- ✅ Création de l'utilisateur avec les bons droits
- ✅ Application des migrations Django

### 4. **Configuration SSL**
- ✅ Génération automatique des certificats Let's Encrypt
- ✅ Renouvellement automatique configuré
- ✅ Redirection HTTP → HTTPS

### 5. **Configuration des services**
- ✅ **Gunicorn** (port 8000) - Application Django
- ✅ **Daphne** (port 8001) - WebSockets
- ✅ **Celery Worker** - Tâches asynchrones
- ✅ **Celery Beat** - Tâches planifiées
- ✅ **Nginx** - Reverse proxy avec SSL

## 🚀 Utilisation

### Prérequis

1. **Fichier `.env` requis** avec les variables suivantes :

```bash
# Base de données
DATABASE_NAME=mobcash_db
DATABASE_USER=mobcash_user
DATABASE_PASSWORD=votre_mot_de_passe_securise
DATABASE_HOST=localhost
DATABASE_PORT=5432

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379

# Django
SECRET_KEY=votre_secret_key_django
DEBUG=False

# Email (optionnel)
EMAIL_HOST=smtp.gmail.com
EMAIL_HOST_USER=votre@email.com
EMAIL_PASSWORD=votre_mot_de_passe

# Base URL
BASE_URL=https://votre-domaine.com

# Ports internes (Multi-projets)
# Utilisez des ports différents pour chaque projet sur le même VPS
APP_PORT=8000       # Port pour Django/Gunicorn
WS_PORT=8001        # Port pour WebSockets/Daphne
```

2. **Nom de domaine** pointant vers votre serveur

### Lancement

```bash
# Rendre le script exécutable
chmod +x init_server.sh

# Lancer l'initialisation
./init_server.sh votre-domaine.com

# Exemple
./init_server.sh api.turaincash.com
```

## 📦 Ce qui est créé

### Services systemd

1. **`/etc/systemd/system/gunicorn_mobcash.service`**
   - Service Gunicorn pour Django
   - 4 workers
   - Timeout 120s
   - Logs dans `logs/gunicorn_*.log`

2. **`/etc/systemd/system/daphne_mobcash.service`**
   - Service Daphne pour WebSockets
   - Écoute sur 127.0.0.1:8001

### Configuration Supervisor

**`/etc/supervisor/conf.d/celery_mobcash.conf`**
- Celery Worker (4 workers concurrents)
- Celery Beat (tâches planifiées)
- Logs dans `logs/celery_*.log`

### Configuration Nginx

**`/etc/nginx/sites-available/mobcash_inte`**
- Reverse proxy vers Gunicorn (port 8000)
- Reverse proxy WebSocket vers Daphne (port 8001)
- Gestion des fichiers statiques et média
- SSL avec Let's Encrypt (si disponible)
- Logs dans `logs/nginx_*.log`

### Dossiers créés

```
/var/www/mobcash/
├── static/     # Fichiers statiques Django
└── media/      # Fichiers uploadés

<projet>/logs/
├── gunicorn_access.log
├── gunicorn_error.log
├── celery_worker.log
├── celery_worker_error.log
├── celery_beat.log
├── celery_beat_error.log
├── nginx_access.log
└── nginx_error.log
```

## 🔧 Gestion des services

### Gunicorn (Django)

```bash
# Redémarrer
sudo systemctl restart gunicorn_mobcash

# Voir le statut
sudo systemctl status gunicorn_mobcash

# Voir les logs
tail -f logs/gunicorn_error.log

# Activer au démarrage
sudo systemctl enable gunicorn_mobcash
```

### Daphne (WebSockets)

```bash
# Redémarrer
sudo systemctl restart daphne_mobcash

# Voir le statut
sudo systemctl status daphne_mobcash

# Activer au démarrage
sudo systemctl enable daphne_mobcash
```

### Celery

```bash
# Redémarrer worker et beat
sudo supervisorctl restart celery_mobcash_worker celery_mobcash_beat

# Voir le statut
sudo supervisorctl status

# Voir les logs
tail -f logs/celery_worker.log

# Recharger la configuration
sudo supervisorctl reread
sudo supervisorctl update
```

### Nginx

```bash
# Redémarrer
sudo systemctl restart nginx

# Recharger la configuration (sans interruption)
sudo systemctl reload nginx

# Tester la configuration
sudo nginx -t

# Voir les logs
tail -f logs/nginx_error.log
```

### PostgreSQL

```bash
# Redémarrer
sudo systemctl restart postgresql

# Se connecter à la base
sudo -u postgres psql -d mobcash_db

# Voir le statut
sudo systemctl status postgresql
```

### Redis

```bash
# Redémarrer
sudo systemctl restart redis-server

# Se connecter
redis-cli

# Voir le statut
sudo systemctl status redis-server
```

## 🔄 Déploiement des mises à jour

Après l'initialisation, utilisez le script `deploy.sh` pour les mises à jour :

```bash
./deploy.sh
```

Ce script :
- Fait un `git pull`
- Active l'environnement virtuel
- Applique les migrations
- Redémarre tous les services

## 🔐 SSL / HTTPS

### Certificats automatiques

Le script génère automatiquement les certificats SSL avec Let's Encrypt si :
- Le domaine pointe vers le serveur
- Le port 80 est accessible depuis Internet

### Générer SSL manuellement

Si l'installation automatique échoue :

```bash
# Arrêter Nginx
sudo systemctl stop nginx

# Générer les certificats
sudo certbot certonly --standalone -d votre-domaine.com

# Redémarrer Nginx
sudo systemctl start nginx
```

### Renouvellement automatique

Le renouvellement est configuré automatiquement avec un timer systemd :

```bash
# Vérifier le timer
sudo systemctl status certbot.timer

# Tester le renouvellement
sudo certbot renew --dry-run
```

## 🐛 Dépannage

### Gunicorn ne démarre pas

```bash
# Voir les logs détaillés
sudo journalctl -u gunicorn_mobcash -n 50

# Vérifier la configuration
source .venv/bin/activate
gunicorn --check-config mobcash_inte_backend.wsgi:application
```

### Celery ne fonctionne pas

```bash
# Voir les logs Supervisor
sudo supervisorctl tail -f celery_mobcash_worker

# Redémarrer
sudo supervisorctl restart celery_mobcash_worker

# Vérifier Redis
redis-cli ping
```

### Nginx erreur 502

```bash
# Vérifier que Gunicorn écoute
sudo netstat -tlnp | grep 8000

# Vérifier les logs Nginx
tail -f logs/nginx_error.log

# Vérifier les logs Gunicorn
tail -f logs/gunicorn_error.log
```

### Base de données inaccessible

```bash
# Vérifier PostgreSQL
sudo systemctl status postgresql

# Tester la connexion
psql -h localhost -U mobcash_user -d mobcash_db

# Voir les logs PostgreSQL
sudo tail -f /var/log/postgresql/postgresql-*-main.log
```

## 📊 Vérification de l'installation

Après l'installation, vérifiez que tout fonctionne :

```bash
# Tous les services
sudo systemctl status gunicorn_mobcash daphne_mobcash nginx postgresql redis-server

# Celery
sudo supervisorctl status

# Ports en écoute
sudo netstat -tlnp | grep -E '(8000|8001|5432|6379|80|443)'

# Test de l'API
curl http://localhost:8000/
curl https://votre-domaine.com/
```

## 🎯 Architecture finale

```
Internet
    ↓
Nginx (port 80/443)
    ├── /static/  → /var/www/mobcash/static/
    ├── /media/   → /var/www/mobcash/media/
    ├── /ws/      → Daphne (port 8001) [WebSockets]
    └── /         → Gunicorn (port 8000) [Django]
                        ↓
                    PostgreSQL (port 5432)
                    Redis (port 6379)
                        ↓
                    Celery Worker + Beat
```

## 📝 Notes importantes

- ✅ Le script détecte et utilise la version Python installée
- ✅ Tous les outils manquants sont installés automatiquement
- ✅ Les services sont configurés pour démarrer automatiquement au boot
- ✅ Les logs sont centralisés dans le dossier `logs/`
- ✅ SSL est configuré automatiquement si possible
- ✅ Le renouvellement SSL est automatique

## 🆘 Support

En cas de problème :

1. Vérifiez les logs dans le dossier `logs/`
2. Vérifiez le statut des services
3. Consultez les logs système : `sudo journalctl -xe`
