# Origine CORS / URL du dashboard, calculée une seule fois et partagée
# (API Gateway, bucket de documents, Lambdas pour les liens dans les emails).
locals {
  frontend_origin = "https://${module.s3_frontend.cloudfront_domain_name}"
  sender_email    = var.sender_email != "" ? var.sender_email : var.admin_email
}

# Suffixe unique et stable pour les ressources dont le nom doit être unique
# au niveau global (buckets S3, domaine Cognito)
resource "random_string" "suffix" {
  length  = 8
  special = false
  upper   = false
}

# ---------------------------------------------------------------------
# Stockage
# ---------------------------------------------------------------------

module "dynamodb" {
  source       = "./modules/dynamodb"
  project_name = var.project_name
  environment  = var.environment
}

module "s3_offres" {
  source       = "./modules/s3_offres"
  project_name = var.project_name
  environment  = var.environment
  suffix       = random_string.suffix.result
}

module "s3_documents" {
  source         = "./modules/s3_documents"
  project_name   = var.project_name
  environment    = var.environment
  suffix         = random_string.suffix.result
  allowed_origin = local.frontend_origin
}

module "s3_frontend" {
  source       = "./modules/s3_frontend"
  project_name = var.project_name
  environment  = var.environment
  suffix       = random_string.suffix.result
}

# ---------------------------------------------------------------------
# Notifications
# ---------------------------------------------------------------------

module "sns" {
  source       = "./modules/sns"
  project_name = var.project_name
  environment  = var.environment
  admin_email  = var.admin_email
  domaines     = var.domaines
}

module "ses" {
  source       = "./modules/ses"
  sender_email = local.sender_email
}

# ---------------------------------------------------------------------
# Authentification
# ---------------------------------------------------------------------

module "cognito" {
  source            = "./modules/cognito"
  project_name      = var.project_name
  environment       = var.environment
  admin_email       = var.admin_email
  domain_suffix     = random_string.suffix.result
  mfa_configuration = var.mfa_configuration

  callback_urls = ["${local.frontend_origin}/index.html"]
  logout_urls   = ["${local.frontend_origin}/login.html"]
}

# ---------------------------------------------------------------------
# IAM (rôles Lambda en moindre privilège)
# ---------------------------------------------------------------------

module "iam" {
  source                  = "./modules/iam"
  project_name            = var.project_name
  environment             = var.environment
  offres_bucket_arn       = module.s3_offres.bucket_arn
  documents_bucket_arn    = module.s3_documents.bucket_arn
  table_offres_arn        = module.dynamodb.table_offres_arn
  table_etudiants_arn     = module.dynamodb.table_etudiants_arn
  table_candidatures_arn  = module.dynamodb.table_candidatures_arn
  table_notifications_arn = module.dynamodb.table_notifications_arn
  table_audit_arn         = module.dynamodb.table_audit_arn
  sns_topic_arns          = values(module.sns.topic_arns_par_domaine)
  cognito_user_pool_arn   = module.cognito.user_pool_arn
  ses_identity_arn        = module.ses.identity_arn
}

# ---------------------------------------------------------------------
# Lambdas
# ---------------------------------------------------------------------

module "lambda" {
  source             = "./modules/lambda"
  project_name       = var.project_name
  environment        = var.environment
  lambda_runtime     = var.lambda_runtime
  log_retention_days = var.log_retention_days
  backend_path       = "${path.module}/../backend"

  lambda_notifier_role_arn  = module.iam.lambda_notifier_role_arn
  lambda_api_role_arn       = module.iam.lambda_api_role_arn
  lambda_scheduler_role_arn = module.iam.lambda_scheduler_role_arn

  table_offres_name        = module.dynamodb.table_offres_name
  table_etudiants_name     = module.dynamodb.table_etudiants_name
  table_candidatures_name  = module.dynamodb.table_candidatures_name
  table_notifications_name = module.dynamodb.table_notifications_name
  table_audit_name         = module.dynamodb.table_audit_name

  sns_topic_arns_par_domaine = module.sns.topic_arns_par_domaine
  cognito_user_pool_id       = module.cognito.user_pool_id
  offres_bucket_arn          = module.s3_offres.bucket_arn
  offres_bucket_name         = module.s3_offres.bucket_name
  documents_bucket_name      = module.s3_documents.bucket_name

  cors_allowed_origin = local.frontend_origin
  dashboard_url       = local.frontend_origin
  sender_email        = module.ses.sender_email
  ses_sandbox_mode    = var.ses_sandbox_mode
  rappel_jours        = var.rappel_jours
}

# Câblage S3 -> Lambda notifier (dépendance croisée entre 2 modules,
# donc placée ici plutôt que dans un seul des deux modules)
resource "aws_s3_bucket_notification" "offres_upload" {
  bucket = module.s3_offres.bucket_id

  lambda_function {
    lambda_function_arn = module.lambda.notifier_function_arn
    events              = ["s3:ObjectCreated:*"]
  }

  depends_on = [module.lambda]
}

# ---------------------------------------------------------------------
# Tâches planifiées (digest hebdo, rappels, clôture auto)
# ---------------------------------------------------------------------

module "schedules" {
  source                  = "./modules/schedules"
  project_name            = var.project_name
  environment             = var.environment
  scheduler_function_arn  = module.lambda.scheduler_function_arn
  scheduler_function_name = module.lambda.scheduler_function_name
  digest_cron             = var.digest_cron
  rappels_cron            = var.rappels_cron
}

# ---------------------------------------------------------------------
# API Gateway
# ---------------------------------------------------------------------

module "api_gateway" {
  source                   = "./modules/api_gateway"
  project_name             = var.project_name
  environment              = var.environment
  cognito_user_pool_arn    = module.cognito.user_pool_arn
  lambda_api_invoke_arn    = module.lambda.api_function_invoke_arn
  lambda_api_function_name = module.lambda.api_function_name
  cors_allowed_origin      = local.frontend_origin
}
