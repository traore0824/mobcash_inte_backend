#!/bin/bash
set -e

echo "🚀 Début du déploiement Mobcash Backend"

# Variables de configuration
PROJECT_DIR="/root/mobcash_inte_backend"
VENV_PATH="$PROJECT_DIR/.venv"
TEST_DIR="$PROJECT_DIR/test_mobcash"
CELERY_WORKERS=2  # à ajuster si nécessaire

# 0. Navigation et activation
echo "📂 Navigation vers le répertoire du projet..."
cd "$PROJECT_DIR"
echo "🗄️ Activation du virtual env..."
source "$VENV_PATH/bin/activate"

# 1. Récupération du code
echo "📥 Git pull..."
git pull origin

# 2. Migrations
echo "🗄️ Création des migrations..."
python manage.py makemigrations
echo "🗄️ Application des migrations..."
python manage.py migrate

# 3. Arrêt temporaire des services pour déploiement
echo "⏹️ Arrêt temporaire de Daphne et Celery..."
sudo supervisorctl stop daphne_mobcash
sudo supervisorctl stop celery_mobcash
sleep 3

# 4. Nettoyage optionnel
echo "🧹 Nettoyage des fichiers temporaires..."
find . -name "*.pyc" -delete
find . -name "__pycache__" -type d -exec rm -rf {} + || true

# 5. Lancer les tests automatisés Django
echo "🧪 Lancement des tests Mobcash..."
cd "$TEST_DIR"

echo "📦 Tests pour les users classiques..."
python "$PROJECT_DIR/manage.py" test user --verbosity=2
RESULT_USER=$?

echo "🤖 Tests pour les users Telegram..."
python "$PROJECT_DIR/manage.py" test telegram --verbosity=2
RESULT_TELEGRAM=$?

# Vérification du résultat des tests
if [ $RESULT_USER -eq 0 ] && [ $RESULT_TELEGRAM -eq 0 ]; then
    echo "✅ Tous les tests ont réussi !"
    read -p "Voulez-vous redémarrer les services maintenant ? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "🔄 Redémarrage des services..."
        sudo systemctl restart gunicorn_mobcash.service
        for i in $(seq 1 $CELERY_WORKERS); do
            celery -A mobcash_inte_backend worker --loglevel=info -n "worker$i@%h" --detach --pidfile="/tmp/celery_worker$i.pid"
        done
        echo "🎉 Services redémarrés avec succès !"
    else
        echo "⚠️ Services non redémarrés. Vous pouvez les redémarrer manuellement après vérification."
    fi
else
    echo "❌ Erreurs détectées dans les tests :"
    if [ $RESULT_USER -ne 0 ]; then
        echo "   - Tests user échoués"
    fi
    if [ $RESULT_TELEGRAM -ne 0 ]; then
        echo "   - Tests telegram échoués"
    fi
    echo "⚠️ Veuillez corriger les erreurs avant de redémarrer les services."
fi

# 6. Statut final
echo ""
echo "📊 Statut actuel des services :"
echo "   - Gunicorn: $(sudo systemctl is-active gunicorn_mobcash.service || echo inactive)"
echo "   - Workers actifs: $(pgrep -c -f 'mobcash_inte_backend worker' || echo 0)"
