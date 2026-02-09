#!/bin/bash
set -e

# --------------------------
# Vérifie le domaine
# --------------------------
DOMAIN=$1
if [ -z "$DOMAIN" ]; then
  echo "Usage: ./init.sh example.com"
  exit 1
fi
echo "Déploiement pour le domaine : $DOMAIN"

# --------------------------
# Vérifie que .env existe
# --------------------------
if [ ! -f .env ]; then
  echo "❌ .env introuvable ! Créez un fichier .env avec vos variables d'environnement avant de lancer."
  exit 1
else
  echo ".env trouvé, utilisation des variables existantes"
fi

# --------------------------
# Génère nginx.conf avec le domaine
# --------------------------
echo "Génération du nginx.conf pour $DOMAIN..."
sed "s/{{DOMAIN}}/$DOMAIN/g" nginx/default.conf.template > nginx/default.conf

# --------------------------
# Build et lancement des containers
# --------------------------
echo "Build et lancement des containers..."
docker compose up -d --build web daphne celery nginx

# --------------------------
# Attente que le container web soit prêt
# --------------------------
echo "Attente que Django soit prêt..."
docker compose exec web python manage.py check

# --------------------------
# Collectstatic et migrations
# --------------------------
echo "Collectstatic, Makemigrations et migrations..."
docker compose exec web python manage.py collectstatic --noinput
docker compose exec web python manage.py makemigrations
docker compose exec web python manage.py migrate

echo "✅ Déploiement terminé pour $DOMAIN !"
echo "Vous pouvez maintenant accéder à https://$DOMAIN"
