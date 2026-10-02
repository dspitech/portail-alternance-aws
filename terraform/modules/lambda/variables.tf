variable "project_name" {
  type = string
}

variable "environment" {
  type = string
}

variable "lambda_runtime" {
  type = string
}

variable "log_retention_days" {
  type = number
}

variable "backend_path" {
  description = "Chemin local vers le dossier backend/ contenant le code des Lambdas"
  type        = string
}

variable "lambda_notifier_role_arn" {
  type = string
}

variable "lambda_api_role_arn" {
  type = string
}

variable "table_offres_name" {
  type = string
}

variable "table_etudiants_name" {
  type = string
}

variable "table_candidatures_name" {
  type = string
}

variable "sns_topic_arns_par_domaine" {
  description = "Map { domaine = topic_arn }"
  type        = map(string)
}

variable "cognito_user_pool_id" {
  type = string
}

variable "offres_bucket_arn" {
  type = string
}

variable "cors_allowed_origin" {
  type = string
}

variable "lambda_scheduler_role_arn" {
  type = string
}

variable "table_notifications_name" {
  type = string
}

variable "table_audit_name" {
  type = string
}

variable "documents_bucket_name" {
  type = string
}

variable "offres_bucket_name" {
  type = string
}

variable "sender_email" {
  type = string
}

variable "dashboard_url" {
  type = string
}

variable "ses_sandbox_mode" {
  type = bool
}

variable "rappel_jours" {
  type = number
}
