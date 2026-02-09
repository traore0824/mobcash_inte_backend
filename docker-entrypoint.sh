#!/bin/bash
set -e

# Attendre que la DB soit prête
echo "Waiting for database..."
while ! pg_isready -h "$DATABASE_HOST" -p "$DATABASE_PORT" -U "$DATABASE_USER"; do
  sleep 1
done
echo "Database is ready!"

# Collect static files
python manage.py collectstatic --noinput

# Appliquer les migrations
python manage.py migrate

# Exécuter la commande passée (Gunicorn / Daphne / Celery)
exec "$@"
