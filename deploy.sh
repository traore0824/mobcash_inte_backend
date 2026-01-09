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
        
        # Redémarrer supervisorctl restart all
        info "Redémarrage de tous les services Supervisor..."
        sudo supervisorctl restart all || {
            error "Erreur lors du redémarrage des services Supervisor"
        }
        
        error "Déploiement annulé à cause d'erreurs de vérification Django"
        exit 1
    fi
else
    warn "Fichier manage.py non trouvé, saut de la vérification Django"
fi

# Étape 3.5: Créer et appliquer les migrations
info "Étape 3.5: Création et application des migrations..."
if [ -f "manage.py" ]; then
    # Créer les migrations
    if python3 manage.py makemigrations; then
        info "Migrations créées avec succès"
    else
        warn "Aucune nouvelle migration à créer ou erreur lors de la création"
    fi
    
    # Appliquer les migrations
    if python3 manage.py migrate; then
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

# Étape 5: Redémarrer tous les services Supervisor
info "Étape 5: Redémarrage des services Supervisor..."

# Trouver tous les fichiers de configuration supervisor
SUPERVISOR_CONF_DIR="/etc/supervisor/conf.d"
if [ -d "$SUPERVISOR_CONF_DIR" ]; then
    # Lister tous les fichiers .conf
    CONFIG_FILES=$(find "$SUPERVISOR_CONF_DIR" -name "*.conf" 2>/dev/null || true)
    
    if [ -n "$CONFIG_FILES" ]; then
        info "Fichiers de configuration Supervisor trouvés:"
        echo "$CONFIG_FILES" | while read -r conf_file; do
            # Extraire le nom du service depuis le nom du fichier
            service_name=$(basename "$conf_file" .conf)
            info "  - $service_name"
        done
        
        # Recharger la configuration supervisor
        if sudo supervisorctl reread; then
            info "Configuration Supervisor rechargée"
        else
            warn "Erreur lors du rechargement de la configuration Supervisor"
        fi
        
        # Mettre à jour les services
        if sudo supervisorctl update; then
            info "Services Supervisor mis à jour"
        else
            warn "Erreur lors de la mise à jour des services Supervisor"
        fi
        
        # Redémarrer tous les services
        if sudo supervisorctl restart all; then
            info "Tous les services Supervisor redémarrés"
        else
            warn "Erreur lors du redémarrage de tous les services Supervisor"
            # Essayer de redémarrer individuellement
            echo "$CONFIG_FILES" | while read -r conf_file; do
                service_name=$(basename "$conf_file" .conf)
                if sudo supervisorctl restart "$service_name"; then
                    info "  ✓ $service_name redémarré"
                else
                    warn "  ✗ Échec du redémarrage de $service_name"
                fi
            done
        fi
        
        # Afficher le statut
        info "Statut des services Supervisor:"
        sudo supervisorctl status || true
    else
        warn "Aucun fichier de configuration Supervisor trouvé dans $SUPERVISOR_CONF_DIR"
    fi
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

echo ""
echo "=========================================="
info "Déploiement terminé avec succès!"
echo "=========================================="
echo ""
info "Résumé:"
info "  - Code mis à jour depuis Git"
info "  - Environnement virtuel activé"
info "  - Vérification Django effectuée"
info "  - Migrations créées et appliquées"
info "  - Gunicorn redémarré"
info "  - Services Supervisor redémarrés"
info "  - Vérifications Python effectuées"
echo ""

