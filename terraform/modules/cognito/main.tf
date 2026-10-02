data "aws_region" "current" {}

resource "aws_cognito_user_pool" "main" {
  name = "${var.project_name}-${var.environment}-users"

  auto_verified_attributes = ["email"]

  password_policy {
    minimum_length    = 10
    require_lowercase = true
    require_uppercase = true
    require_numbers   = true
    require_symbols   = false
  }

  username_attributes = ["email"]

  # MFA TOTP (application d'authentification). "ON" = obligatoire pour TOUS les
  # utilisateurs (Cognito ne sait pas l'imposer par groupe). "OPTIONAL" = activable
  # par chaque utilisateur.
  mfa_configuration = var.mfa_configuration

  dynamic "software_token_mfa_configuration" {
    for_each = var.mfa_configuration == "OFF" ? [] : [1]
    content {
      enabled = true
    }
  }

  admin_create_user_config {
    allow_admin_create_user_only = true
  }

  schema {
    name                = "email"
    attribute_data_type = "String"
    mutable             = true
    required            = true
  }
}

resource "aws_cognito_user_pool_domain" "main" {
  domain       = "${var.project_name}-${var.environment}-${var.domain_suffix}"
  user_pool_id = aws_cognito_user_pool.main.id
}

resource "aws_cognito_user_pool_client" "dashboard" {
  name         = "${var.project_name}-${var.environment}-dashboard-client"
  user_pool_id = aws_cognito_user_pool.main.id

  generate_secret                     = false
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_flows                  = ["code"]
  allowed_oauth_scopes                 = ["openid", "email", "profile"]
  supported_identity_providers         = ["COGNITO"]

  callback_urls = var.callback_urls
  logout_urls   = var.logout_urls

  explicit_auth_flows = [
    "ALLOW_USER_SRP_AUTH",
    "ALLOW_REFRESH_TOKEN_AUTH",
    "ALLOW_USER_PASSWORD_AUTH"
  ]
}

resource "aws_cognito_user_group" "admins" {
  name         = "Admins"
  user_pool_id = aws_cognito_user_pool.main.id
  description  = "Équipe recrutement / pilotage de la plateforme"
  precedence   = 1
}

resource "aws_cognito_user_group" "recruteurs" {
  name         = "Recruteurs"
  user_pool_id = aws_cognito_user_pool.main.id
  description  = "Entreprises partenaires : publient leurs offres et gèrent leurs candidatures"
  precedence   = 2
}

resource "aws_cognito_user_group" "etudiants" {
  name         = "Etudiants"
  user_pool_id = aws_cognito_user_pool.main.id
  description  = "Étudiants consultant/postulant aux offres"
  precedence   = 3
}

# Premier compte admin, créé directement par Terraform pour amorcer le
# système (mot de passe temporaire à changer à la première connexion)
resource "aws_cognito_user" "first_admin" {
  user_pool_id   = aws_cognito_user_pool.main.id
  username       = var.admin_email
  desired_delivery_mediums = ["EMAIL"]

  attributes = {
    email          = var.admin_email
    email_verified = "true"
  }
}

resource "aws_cognito_user_in_group" "first_admin" {
  user_pool_id = aws_cognito_user_pool.main.id
  username     = aws_cognito_user.first_admin.username
  group_name   = aws_cognito_user_group.admins.name
}
