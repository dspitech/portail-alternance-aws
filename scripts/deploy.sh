#!/usr/bin/env bash
# Déploiement complet : terraform apply, puis génération de la config
# frontend à partir des outputs, puis upload du dashboard sur S3/CloudFront.
#
# Prérequis : terraform, aws cli configuré, jq
set -euo pipefail

cd "$(dirname "$0")/../terraform"

echo "==> terraform init"
terraform init

echo "==> terraform apply"
terraform apply -auto-approve

echo "==> Récupération des outputs"
API_URL=$(terraform output -raw api_url)
COGNITO_DOMAIN=$(terraform output -raw cognito_hosted_ui_domain)
COGNITO_CLIENT_ID=$(terraform output -raw cognito_client_id)
FRONTEND_BUCKET=$(terraform output -raw frontend_bucket_name)
CLOUDFRONT_DOMAIN=$(terraform output -raw dashboard_url)
DISTRIBUTION_ID=$(terraform output -raw cloudfront_distribution_id)

cd ../frontend

echo "==> Génération de js/config.js"
cat > js/config.js <<EOF
const CONFIG = {
  API_BASE_URL: "${API_URL}",
  COGNITO_DOMAIN: "${COGNITO_DOMAIN}",
  COGNITO_CLIENT_ID: "${COGNITO_CLIENT_ID}",
  COGNITO_REDIRECT_URI: window.location.origin + "/index.html",
  COGNITO_LOGOUT_URI: window.location.origin + "/login.html",
};
EOF

echo "==> Upload vers s3://${FRONTEND_BUCKET}"
aws s3 sync . "s3://${FRONTEND_BUCKET}" \
  --exclude ".git/*" \
  --exclude "tests/*" \
  --exclude "node_modules/*" \
  --cache-control "no-cache"

echo "==> Invalidation du cache CloudFront"
aws cloudfront create-invalidation --distribution-id "${DISTRIBUTION_ID}" --paths "/*" >/dev/null

echo ""
echo "Dashboard déployé : ${CLOUDFRONT_DOMAIN}"
echo "(la première propagation CloudFront peut prendre quelques minutes)"
