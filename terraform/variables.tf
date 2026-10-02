variable "project_name" {
  description = "Nom du projet, utilisé comme préfixe pour toutes les ressources"
  type        = string
  default     = "alternance-alerts"
}

variable "environment" {
  description = "Environnement de déploiement (dev, staging, prod)"
  type        = string
  default     = "dev"
}

variable "region" {
  description = "Région AWS de déploiement"
  type        = string
  default     = "eu-west-3"
}

variable "admin_email" {
  description = "Email du premier compte admin (créé dans Cognito et abonné aux alertes SNS)"
  type        = string
}

variable "domaines" {
  description = "Liste des domaines métier gérés par la plateforme (utilisée pour le mapping préfixe fichier -> domaine)"
  type        = list(string)
  default     = ["Cloud", "Cyber", "Archi", "Web", "General"]
}

variable "lambda_runtime" {
  description = "Runtime Python pour les fonctions Lambda"
  type        = string
  default     = "python3.12"
}

variable "log_retention_days" {
  description = "Durée de rétention des logs CloudWatch"
  type        = number
  default     = 30
}

variable "sender_email" {
  description = "Adresse expéditrice SES (emails de statut, digest, rappels). Vide = admin_email."
  type        = string
  default     = ""
}

variable "ses_sandbox_mode" {
  description = "true tant que SES est en sandbox : l'API vérifie automatiquement les destinataires. Passer à false après la sortie de sandbox."
  type        = bool
  default     = true
}

variable "mfa_configuration" {
  description = "MFA TOTP Cognito : OFF | OPTIONAL | ON. ON = obligatoire pour tous les utilisateurs (admins compris)."
  type        = string
  default     = "OPTIONAL"
}

variable "digest_cron" {
  description = "Planification (EventBridge, UTC) du résumé hebdomadaire"
  type        = string
  default     = "cron(0 7 ? * MON *)"
}

variable "rappels_cron" {
  description = "Planification (EventBridge, UTC) des rappels de date limite et de la clôture automatique"
  type        = string
  default     = "cron(0 8 * * ? *)"
}

variable "rappel_jours" {
  description = "Nombre de jours avant la date limite pour envoyer le rappel"
  type        = number
  default     = 3
}
