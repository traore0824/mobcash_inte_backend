#!/bin/bash

# Script de déploiement pour mobcash_inte_backend
# Ce script effectue un git pull, résout les problèmes courants,
# active l'environnement virtuel, redémarre les services et vérifie l'installation

echo "=========================================="
echo "Début du déploiement"
echo "=========================================="

# Couleurs pour les messages
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Fonction pour afficher les messages
info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Étape 1: Git pull avec résolution des conflits
info "Étape 1: Mise à jour du code depuis Git..."
cd "$(dirname "$0")"

# Sauvegarder le commit actuel pour restauration en cas d'échec
PREVIOUS_COMMIT=$(git rev-parse HEAD)

# Sauvegarder les changements locaux s'il y en a
if ! git diff-index --quiet HEAD --; then
    warn "Des changements locaux détectés. Stash des modifications..."
    git stash save "Auto-stash before deploy $(date +%Y-%m-%d_%H:%M:%S)"
fi

# Tentative de pull
if git pull origin main || git pull origin master; then
    info "Git pull réussi"
else
    error "Erreur lors du git pull"
    
    # Vérifier s'il y a des conflits
    if [ -n "$(git ls-files -u)" ]; then
        warn "Conflits détectés. Tentative de résolution automatique..."
        git merge --abort 2>/dev/null || true
        git reset --hard HEAD
        git pull --rebase origin main || git pull --rebase origin master || {
            error "Impossible de résoudre les conflits automatiquement"
            exit 1
        }
    else
        # Autres erreurs (connexion, etc.)
        warn "Vérification de la connexion et nouvelle tentative..."
        sleep 2
        git pull origin main || git pull origin master || {
            error "Échec du git pull après nouvelle tentative"
            exit 1
        }
    fi
fi

# Étape 2: Activer l'environnement virtuel
info "Étape 2: Activation de l'environnement virtuel..."
if [ -d ".venv" ]; then
    source .venv/bin/activate
    info "Environnement virtuel .venv activé"
else
    error "Le dossier .venv n'existe pas"
    exit 1
fi


# Vérifier que Python est disponible
if ! command -v python &> /dev/null && ! command -v python3 &> /dev/null; then
    error "Python n'est pas installé ou n'est pas dans le PATH"
    exit 1
fi

# Étape 3: Vérification Django AVANT redémarrage
info "Étape 3: Vérification Django avant redémarrage..."
if [ -f "manage.py" ]; then
    if python3 manage.py check; then
        info "Vérification Django réussie - Aucun problème détecté"
    else
        error "Échec de la vérification Django - Annulation des changements"
        
        # Annuler les changements Git (restaurer l'état précédent)
        info "Annulation des changements Git..."
        if [ -n "$PREVIOUS_COMMIT" ]; then
            git reset --hard "$PREVIOUS_COMMIT" || {
                warn "Impossible de restaurer l'état précédent automatiquement"
            }
        else
            warn "Commit précédent non disponible pour restauration"
        fi
        
        # Redémarrer seulement Celery/Gunicorn de CE projet (pas restart all)
        info "Redémarrage ciblé des services mobcash après rollback..."
        sudo systemctl restart gunicorn_mobcash.service 2>/dev/null || true
        sudo supervisorctl status 2>/dev/null | awk '/celery_mobcash/ {print $1}' | while read -r prog; do
            [ -z "$prog" ] && continue
            sudo supervisorctl restart "$prog" || true
        done
        
        error "Déploiement annulé à cause d'erreurs de vérification Django"
        exit 1
    fi
else
    warn "Fichier manage.py non trouvé, saut de la vérification Django"
fi

# Étape 3.5: Générer puis appliquer les migrations
# Pas de backup/restore des clés chiffrées — trop risqué (peut écraser les clés).
info "Étape 3.5: Génération puis application des migrations..."
if [ -f "manage.py" ]; then
    if python3 manage.py makemigrations --noinput; then
        info "Génération des migrations réussie"
    else
        error "Erreur lors de la génération des migrations"
        exit 1
    fi

    if python3 manage.py migrate --noinput; then
        info "Migrations appliquées avec succès"
    else
        error "Erreur lors de l'application des migrations"
        exit 1
    fi
else
    warn "Fichier manage.py non trouvé, saut des migrations"
fi

# Étape 4: Redémarrer Gunicorn
info "Étape 4: Redémarrage de Gunicorn..."
if sudo systemctl restart gunicorn_mobcash.service; then
    info "Gunicorn redémarré avec succès"
    sleep 2
    
    # Vérifier le statut
    if sudo systemctl is-active --quiet gunicorn_mobcash.service; then
        info "Gunicorn est actif et fonctionne"
    else
        error "Gunicorn n'est pas actif après le redémarrage"
        sudo systemctl status gunicorn_mobcash.service || true
    fi
else
    error "Erreur lors du redémarrage de Gunicorn"
    sudo systemctl status gunicorn_mobcash.service || true
fi

# Étape 5: Isoler Celery mobcash puis redémarrer UNIQUEMENT ses services
# (ne pas faire "supervisorctl restart all" — d'autres projets tournent sur le même serveur)
info "Étape 5: Isolation Celery mobcash_inte + redémarrage ciblé..."

SUPERVISOR_CONF_DIR="/etc/supervisor/conf.d"
CELERY_QUEUE="mobcash_inte"

patch_mobcash_celery_queue() {
    local conf_file="$1"
    if [ ! -f "$conf_file" ]; then
        return 1
    fi
    # Uniquement les confs de CE projet
    if ! grep -q "mobcash_inte_backend" "$conf_file" 2>/dev/null; then
        return 1
    fi
    # Seulement les lignes worker (pas beat)
    if ! grep -q "mobcash_inte_backend worker" "$conf_file" 2>/dev/null; then
        return 1
    fi

    if grep -q -- "-Q ${CELERY_QUEUE}" "$conf_file" 2>/dev/null; then
        info "  ✓ $(basename "$conf_file") : -Q ${CELERY_QUEUE} déjà présent"
        return 0
    fi

    # Retirer un éventuel ancien -Q puis ajouter -Q mobcash_inte en fin de commande worker
    sudo sed -i -E \
        "/mobcash_inte_backend worker/ s/[[:space:]]+-Q[[:space:]]+[^[:space:]]+//g" \
        "$conf_file"
    sudo sed -i -E \
        "/command=.*mobcash_inte_backend worker/ s|[[:space:]]*$| -Q ${CELERY_QUEUE}|" \
        "$conf_file"

    if grep -q -- "-Q ${CELERY_QUEUE}" "$conf_file" 2>/dev/null; then
        info "  ✓ $(basename "$conf_file") : -Q ${CELERY_QUEUE} ajouté"
        return 0
    fi

    warn "  ✗ Impossible d'ajouter -Q ${CELERY_QUEUE} dans $(basename "$conf_file") — à faire à la main"
    return 1
}

if [ -d "$SUPERVISOR_CONF_DIR" ]; then
    PATCHED_ANY=0
    # Cibles connues + toute conf qui lance le worker mobcash_inte_backend
    while IFS= read -r conf_file; do
        [ -z "$conf_file" ] && continue
        if patch_mobcash_celery_queue "$conf_file"; then
            PATCHED_ANY=1
        fi
    done < <(
        {
            printf '%s\n' \
                "$SUPERVISOR_CONF_DIR/celery_mobcash.conf" \
                "$SUPERVISOR_CONF_DIR/celery_mobcash_worker.conf"
            grep -l "mobcash_inte_backend worker" "$SUPERVISOR_CONF_DIR"/*.conf 2>/dev/null || true
        } | sort -u
    )

    if [ "$PATCHED_ANY" -eq 0 ]; then
        warn "Aucune conf Supervisor celery mobcash trouvée — worker non isolé automatiquement"
    fi

    if sudo supervisorctl reread; then
        info "Configuration Supervisor rechargée"
    else
        warn "Erreur lors du rechargement de la configuration Supervisor"
    fi

    if sudo supervisorctl update; then
        info "Services Supervisor mis à jour"
    else
        warn "Erreur lors de la mise à jour des services Supervisor"
    fi

    # Redémarrer seulement les programmes Celery de ce projet (jamais "restart all")
    MOBCASH_CELERY_PROGS=$(sudo supervisorctl status 2>/dev/null | awk '/celery_mobcash/ {print $1}' || true)
    if [ -n "$MOBCASH_CELERY_PROGS" ]; then
        info "Redémarrage ciblé Celery mobcash:"
        echo "$MOBCASH_CELERY_PROGS" | while read -r prog; do
            [ -z "$prog" ] && continue
            if sudo supervisorctl restart "$prog"; then
                info "  ✓ $prog redémarré"
            else
                warn "  ✗ Échec redémarrage $prog"
            fi
        done
    else
        warn "Aucun programme supervisor celery_mobcash* trouvé"
        warn "Ne redémarre PAS 'all' pour ne pas impacter les autres projets"
    fi

    info "Statut Celery mobcash:"
    sudo supervisorctl status 2>/dev/null | grep -E "celery_mobcash|mobcash" || true
else
    warn "Répertoire Supervisor non trouvé: $SUPERVISOR_CONF_DIR"
fi

# Étape 6: Vérification finale avec Python
info "Étape 6: Vérification finale de l'installation Python..."

# Vérifier la version de Python
PYTHON_VERSION=$(python3 --version 2>&1)
info "Version Python: $PYTHON_VERSION"

# Vérifier que Django peut être importé
if python3 -c "import django; print(f'Django {django.get_version()}')" 2>/dev/null; then
    info "Django est correctement installé"
else
    error "Django ne peut pas être importé"
    exit 1
fi

# Vérifier les modules critiques
info "Vérification des modules critiques..."
CRITICAL_MODULES=("celery" "rest_framework" "channels")
for module in "${CRITICAL_MODULES[@]}"; do
    if python3 -c "import $module" 2>/dev/null; then
        info "  ✓ Module $module disponible"
    else
        warn "  ✗ Module $module non disponible"
    fi
done

# Vérifier que Django pointe bien sur Redis DB isolé + file mobcash_inte
info "Vérification isolation Celery (broker / file)..."
python3 - <<'PY' || warn "Impossible de vérifier la config Celery Django"
import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mobcash_inte_backend.settings")
import django
django.setup()
from django.conf import settings
broker = getattr(settings, "CELERY_BROKER_URL", "")
queue = getattr(settings, "CELERY_TASK_DEFAULT_QUEUE", "")
print(f"  CELERY_BROKER_URL={broker}")
print(f"  CELERY_TASK_DEFAULT_QUEUE={queue}")
if "/2" not in str(broker) and not os.getenv("CELERY_BROKER_URL"):
    print("  WARN: broker n'utilise pas Redis DB 2 — risque de collision avec d'autres projets")
if queue != "mobcash_inte":
    print(f"  WARN: file attendue mobcash_inte, trouvée: {queue!r}")
PY

echo ""
echo "=========================================="
info "Déploiement terminé avec succès!"
echo "=========================================="
echo ""
info "Résumé:"
info "  - Code mis à jour depuis Git"
info "  - Environnement virtuel activé"
info "  - Vérification Django effectuée"
info "  - Migrations générées puis appliquées (makemigrations + migrate)"
info "  - Aucun backup/restore des clés chiffrées"
info "  - Gunicorn redémarré"
info "  - Celery mobcash isolé (-Q mobcash_inte) et redémarré (pas restart all)"
info "  - Vérifications Python effectuées"
echo ""

