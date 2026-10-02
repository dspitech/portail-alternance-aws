resource "aws_s3_bucket" "offres" {
  bucket = "${var.project_name}-${var.environment}-offres-${var.suffix}"
}

resource "aws_s3_bucket_public_access_block" "offres" {
  bucket                  = aws_s3_bucket.offres.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "offres" {
  bucket = aws_s3_bucket.offres.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "offres" {
  bucket = aws_s3_bucket.offres.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Le déclenchement Lambda (notification_configuration) est câblé dans le
# main.tf racine car il crée une dépendance croisée avec le module lambda.
