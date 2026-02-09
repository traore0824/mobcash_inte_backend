# 1️⃣ Image de base
FROM python:3.11-slim

# 2️⃣ Variables d’environnement pour python
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 3️⃣ Installer les dépendances système nécessaires
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    postgresql-client \
    gettext \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 4️⃣ Créer le répertoire de travail
WORKDIR /app

# 5️⃣ Copier les fichiers de requirements et installer
COPY requirements.txt .
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# 6️⃣ Copier le code du projet
COPY . .

# 7️⃣ Créer les dossiers pour static et media (persistants via volumes)
RUN mkdir -p /var/www/mobcash/static /var/www/mobcash/media

# 8️⃣ Entrypoint pour collectstatic et migrations (optionnel)
# Ce script peut être exécuté dans init.sh ou manuellement
COPY docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

# 9️⃣ Définir le point d’entrée
ENTRYPOINT ["/app/docker-entrypoint.sh"]
