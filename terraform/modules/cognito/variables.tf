variable "project_name" {
  type = string
}

variable "environment" {
  type = string
}

variable "admin_email" {
  type = string
}

variable "domain_suffix" {
  description = "Suffixe unique pour le domaine hébergé Cognito (doit être globalement unique)"
  type        = string
}

variable "callback_urls" {
  description = "URLs autorisées après login (l'URL CloudFront du dashboard)"
  type        = list(string)
}

variable "logout_urls" {
  description = "URLs autorisées après logout"
  type        = list(string)
}

variable "mfa_configuration" {
  description = "OFF | OPTIONAL | ON (TOTP)"
  type        = string
  default     = "OPTIONAL"

  validation {
    condition     = contains(["OFF", "OPTIONAL", "ON"], var.mfa_configuration)
    error_message = "mfa_configuration doit valoir OFF, OPTIONAL ou ON."
  }
}
