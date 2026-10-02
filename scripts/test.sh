#!/usr/bin/env bash
# Lance toutes les vérifications locales (aucun compte AWS nécessaire).
set -euo pipefail
cd "$(dirname "$0")/.."

echo "==> Backend (pytest + moto)"
pip install -q -r backend/tests/requirements.txt
python3 -m pytest backend/tests -q

echo "==> Contrat frontend/API : régénération des fixtures depuis la vraie API"
EXPORT_FIXTURES=1 python3 -m pytest backend/tests/test_export_fixtures.py -q

echo "==> Frontend (jsdom)"
( cd frontend/tests && npm install --silent && npm test )

echo "==> Terraform"
if command -v terraform >/dev/null; then
  ( cd terraform && terraform init -backend=false -input=false >/dev/null && terraform validate )
else
  echo "terraform non installé : lancez 'terraform init -backend=false && terraform validate' dans terraform/"
fi
