variable "project_name" {
  type = string
}

variable "environment" {
  type = string
}

variable "cognito_user_pool_arn" {
  type = string
}

variable "lambda_api_invoke_arn" {
  type = string
}

variable "lambda_api_function_name" {
  type = string
}

variable "cors_allowed_origin" {
  description = "Origine autorisée pour le CORS (URL CloudFront du dashboard, ou * en dev)"
  type        = string
  default     = "*"
}
