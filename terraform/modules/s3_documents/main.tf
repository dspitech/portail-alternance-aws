# Bucket PRIVÉ pour les CV et lettres de motivation.
# Les étudiants déposent via une URL de POST présignée (limite de taille et de
# type imposée par la policy signée), les admins/recruteurs lisent via une URL
# présignée de courte durée. Aucun accès public.

resource "aws_s3_bucket" "documents" {
  bucket = "${var.project_name}-${var.environment}-documents-${var.suffix}"
}

resource "aws_s3_bucket_public_access_block" "documents" {
  bucket                  = aws_s3_bucket.documents.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "documents" {
  bucket = aws_s3_bucket.documents.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Le navigateur poste directement vers S3 : CORS restreint au dashboard
resource "aws_s3_bucket_cors_configuration" "documents" {
  bucket = aws_s3_bucket.documents.id

  cors_rule {
    allowed_methods = ["POST", "GET"]
    allowed_origins = [var.allowed_origin]
    allowed_headers = ["*"]
    max_age_seconds = 3000
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "documents" {
  bucket = aws_s3_bucket.documents.id

  rule {
    id     = "abort-incomplete-uploads"
    status = "Enabled"
    filter {}
    abort_incomplete_multipart_upload {
      days_after_initiation = 1
    }
  }
}
