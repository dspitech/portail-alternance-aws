variable "project_name" {
  type = string
}

variable "environment" {
  type = string
}

variable "offres_bucket_arn" {
  type = string
}

variable "documents_bucket_arn" {
  type = string
}

variable "table_offres_arn" {
  type = string
}

variable "table_etudiants_arn" {
  type = string
}

variable "table_candidatures_arn" {
  type = string
}

variable "table_notifications_arn" {
  type = string
}

variable "table_audit_arn" {
  type = string
}

variable "sns_topic_arns" {
  type = list(string)
}

variable "cognito_user_pool_arn" {
  type = string
}

variable "ses_identity_arn" {
  type = string
}
