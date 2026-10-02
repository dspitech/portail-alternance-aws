resource "aws_dynamodb_table" "offres" {
  name         = "${var.project_name}-${var.environment}-Offres"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "ID"

  attribute {
    name = "ID"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }
}

resource "aws_dynamodb_table" "etudiants" {
  name         = "${var.project_name}-${var.environment}-Etudiants"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "Email"

  attribute {
    name = "Email"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }
}

resource "aws_dynamodb_table" "candidatures" {
  name         = "${var.project_name}-${var.environment}-Candidatures"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "ID"

  attribute {
    name = "ID"
    type = "S"
  }

  attribute {
    name = "OffreID"
    type = "S"
  }

  attribute {
    name = "EtudiantEmail"
    type = "S"
  }

  # Permet à l'API : "toutes les candidatures d'une offre" sans scan complet
  global_secondary_index {
    name            = "OffreID-index"
    hash_key        = "OffreID"
    projection_type = "ALL"
  }

  # Permet à l'API : "toutes les candidatures d'un étudiant" sans scan complet
  global_secondary_index {
    name            = "EtudiantEmail-index"
    hash_key        = "EtudiantEmail"
    projection_type = "ALL"
  }

  point_in_time_recovery {
    enabled = true
  }
}

# Historique des envois (nouvelle offre, rappels, digest, changements de statut)
resource "aws_dynamodb_table" "notifications" {
  name         = "${var.project_name}-${var.environment}-Notifications"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "ID"

  attribute {
    name = "ID"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }
}

# Journal d'audit : qui a fait quoi, quand
resource "aws_dynamodb_table" "audit" {
  name         = "${var.project_name}-${var.environment}-Audit"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "ID"

  attribute {
    name = "ID"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }
}
