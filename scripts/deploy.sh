#!/bin/bash
set -e

echo "🚀 Starting EmoScreen deployment"

# Always run from project root
cd /var/www/EmoScreen

echo "📥 Pulling latest code from GitHub"
git pull origin main

echo "🐍 Activating virtual environment"
source /var/www/venv/bin/activate

echo "📦 Installing Python dependencies"
pip install --upgrade pip
pip install -r requirements.txt

echo "🗄 Running Django migrations"
python manage.py migrate --noinput

echo "🎨 Collecting static files"
python manage.py collectstatic --noinput

# =====================================================
# 🔽 INGESTION COMMANDS CAN BE ADDED BELOW THIS LINE 🔽
# =====================================================

# Example (commented on purpose):
# python manage.py ingest_data
# python manage.py load_reports
# python scripts/custom_ingest.py

# =====================================================

echo "🔄 Restarting Gunicorn service"
sudo systemctl restart gunicorn-EmoScreen_new

echo "✅ Deployment completed successfully"
