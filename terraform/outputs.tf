output "dashboard_url" {
  description = "URL du dashboard admin (à ouvrir dans le navigateur)"
  value       = "https://${module.s3_frontend.cloudfront_domain_name}"
}

output "api_url" {
  description = "URL de base de l'API (à coller dans frontend/js/api.js -> API_BASE_URL)"
  value       = module.api_gateway.invoke_url
}

output "cognito_hosted_ui_domain" {
  value = module.cognito.hosted_ui_domain
}

output "cognito_user_pool_id" {
  value = module.cognito.user_pool_id
}

output "cognito_client_id" {
  value = module.cognito.user_pool_client_id
}

output "frontend_bucket_name" {
  value = module.s3_frontend.bucket_name
}

output "cloudfront_distribution_id" {
  value = module.s3_frontend.cloudfront_distribution_id
}

output "offres_bucket_name" {
  description = "Bucket où déposer les fichiers d'offres (ex: Cloud_Offre.pdf)"
  value       = module.s3_offres.bucket_name
}

output "sns_topics_par_domaine" {
  value = module.sns.topic_arns_par_domaine
}

output "premier_admin_email" {
  description = "Un mot de passe temporaire a été envoyé à cette adresse par Cognito"
  value       = var.admin_email
}

output "documents_bucket_name" {
  description = "Bucket privé des CV et lettres de motivation"
  value       = module.s3_documents.bucket_name
}

output "ses_sender_email" {
  description = "Cliquer sur le lien de vérification envoyé par AWS à cette adresse"
  value       = module.ses.sender_email
}
