#!/bin/bash
set -e

echo "🚀 Début du déploiement Mobcash Backend"

PROJECT_DIR="/root/mobcash_inte_backend"
VENV_PATH="$PROJECT_DIR/.venv"
CELERY_WORKERS=2

cd "$PROJECT_DIR"
source "$VENV_PATH/bin/activate"

echo "📥 Git pull..."
git pull origin

echo "🗄️ Migrations..."
python manage.py makemigrations
python manage.py migrate

echo "⏹️ Arrêt temporaire de Daphne et Celery..."
sudo supervisorctl stop daphne_mobcash
sudo supervisorctl stop celery_mobcash
sleep 3

echo "🧹 Nettoyage fichiers temporaires..."
find . -name "*.pyc" -delete
find . -name "__pycache__" -type d -exec rm -rf {} + || true

# echo "🧪 Lancement des tests Mobcash..."
# python manage.py test test_mobcash.user test_mobcash.telegram --verbosity=2
# RESULT=$?

# if [ $RESULT -eq 0 ]; then
#     echo "✅ Tous les tests ont réussi !"
#     read -p "Voulez-vous redémarrer les services maintenant ? (y/N): " -n 1 -r
#     echo
#     if [[ $REPLY =~ ^[Yy]$ ]]; then
#         echo "🔄 Redémarrage des services..."
#         sudo systemctl restart gunicorn_mobcash.service
#         for i in $(seq 1 $CELERY_WORKERS); do
#             PID_FILE="/tmp/celery_worker$i.pid"
#             [ -f "$PID_FILE" ] && kill -9 $(cat "$PID_FILE") || true
#             celery -A mobcash_inte_backend worker --loglevel=info -n "worker$i@%h" --detach --pidfile="$PID_FILE"
#         done
#         echo "🎉 Services redémarrés avec succès !"
#     else
#         echo "⚠️ Services non redémarrés."
#     fi
# else
#     echo "❌ Certains tests ont échoué. Veuillez corriger les erreurs avant de redémarrer."
# fi

echo ""
echo "📊 Statut actuel :"
echo "   - Gunicorn: $(sudo systemctl is-active gunicorn_mobcash.service || echo inactive)"
echo "   - Workers actifs: $(pgrep -c -f 'mobcash_inte_backend worker' || echo 0)"
