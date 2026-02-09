#!/bin/bash
set -e

# Attendre que la DB soit prête
echo "Waiting for database..."
while ! pg_isready -h "$DATABASE_HOST" -p "$DATABASE_PORT" -U "$DATABASE_USER"; do
  sleep 1
done
echo "Database is ready!"


# --------------------------
# NOTE: Les migrations et collectstatic sont gérés par init.sh
# pour éviter les conflits (race conditions) entre les conteneurs.
# --------------------------


# Exécuter la commande passée (Gunicorn / Daphne / Celery)
exec "$@"
