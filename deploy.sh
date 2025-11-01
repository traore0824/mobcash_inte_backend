#!/bin/bash
set -e

echo "🚀 Début du déploiement Mobcash Backend"

# Variables de configuration
PROJECT_DIR="/root/mobcash_inte_backend"
VENV_PATH="$PROJECT_DIR/.venv"

# 0. Navigation et activation
echo "📂 Navigation vers le répertoire du projet..."
cd "$PROJECT_DIR"

echo "🗄️ Activation du virtual env..."
source "$VENV_PATH/bin/activate"

# 1. Récupération du code
echo "📥 Git pull..."
git pull origin
#!/bin/bash
set -e  # Arrêter en cas d'erreur

# 2. Migrations
echo "🗄️ Création des migrations..."
python manage.py makemigrations

echo "🗄️ Application des migrations..."
python manage.py migrate

# 3. Arrêt des services
echo "⏹️ Arrêt de Daphne..."
sudo supervisorctl stop daphne_mobcash

echo "⏹️ Arrêt des workers Celery (via Supervisor)..."
sudo supervisorctl stop celery_mobcash

# Attendre que les workers s'arrêtent complètement
sleep 3

# 4. Redémarrage des services
echo ""
echo "🔄 Redémarrage Gunicorn..."
sudo systemctl restart gunicorn_mobcash.service

echo "🔄 Démarrage des workers Celery..."
sleep 2  # Attendre que Beat démarre complètement

# Démarrer les workers avec noms uniques
for i in $(seq 1 $CELERY_WORKERS); do
    echo "   Starting worker$i..."
    celery -A mobcash_inte_backend worker --loglevel=info -n "worker$i@%h" --detach --pidfile="/tmp/celery_worker$i.pid"
done

# 7. Vérifications post-déploiement
echo "✅ Vérification des services..."

echo "--- Gunicorn Status ---"
sudo systemctl status gunicorn_mobcash.service --no-pager -l

echo "--- Supervisor Status ---"
sudo supervisorctl status

echo "--- Workers Celery ---"
sleep 3  # Attendre que les workers démarrent
celery -A mobcash_inte_backend inspect ping || echo "⚠️ Certains workers ne répondent pas encore"

echo "--- Vérification des tâches programmées ---"
celery -A mobcash_inte_backend inspect scheduled | head -10

# 8. Nettoyage optionnel
echo "🧹 Nettoyage des fichiers temporaires..."
find . -name "*.pyc" -delete
find . -name "__pycache__" -type d -exec rm -rf {} + || true

# 9. Test de santé rapide
echo "🏥 Test de santé du système..."
python manage.py check --deploy || echo "⚠️ Certaines vérifications ont échoué"

echo ""
echo "🎉 Déploiement terminé avec succès !"
echo ""
echo "📊 Statut final des services :"
echo "   - Gunicorn: $(sudo systemctl is-active gunicorn_mobcash.service)"
echo "   - Workers: $(pgrep -c -f 'mobcash_inte_backend worker' || echo 0) actifs"

echo ""
echo "📋 Commandes utiles post-déploiement :"
echo "   - Logs daphne: tail -f /var/log/daphne_mobcash.log"
echo "   - Logs Celery: tail -f /var/log/celery_mobcash.log"
echo "   - Logs Gunicorn: sudo journalctl -u gunicorn_mobcash.service -f"
echo "   - Logs transactions: tail -f logs/transactions.log"
echo "   - Workers status: celery -A mobcash_inte_backend inspect active"
# echo "   - Restart workers: sudo supervisorctl restart celery_beat_box"
echo "   - Restart workers: sudo supervisorctl restart daphne_mobcash"
echo "   - Supervisor status: sudo supervisorctl status"
echo ""

# Optionnel : Afficher les logs
read -p "Voulez-vous afficher les logs en temps réel ? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "📜 Affichage des logs transactions (Ctrl+C pour quitter)..."
    tail -f logs/transactions.log
fi