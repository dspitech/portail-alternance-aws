data "archive_file" "notifier" {
  type        = "zip"
  source_dir  = "${var.backend_path}/lambda_notifier"
  output_path = "${path.module}/build/lambda_notifier.zip"
}

data "archive_file" "api" {
  type        = "zip"
  source_dir  = "${var.backend_path}/lambda_api"
  output_path = "${path.module}/build/lambda_api.zip"
}

data "archive_file" "scheduler" {
  type        = "zip"
  source_dir  = "${var.backend_path}/lambda_scheduler"
  output_path = "${path.module}/build/lambda_scheduler.zip"
}

locals {
  common_env = {
    TABLE_OFFRES        = var.table_offres_name
    TABLE_ETUDIANTS     = var.table_etudiants_name
    TABLE_NOTIFICATIONS = var.table_notifications_name
    SNS_TOPIC_ARNS      = jsonencode(var.sns_topic_arns_par_domaine)
    DASHBOARD_URL       = var.dashboard_url
  }
}

# ---------------------------------------------------------------------
# Notifier : déclenchée par un upload dans le bucket des offres
# ---------------------------------------------------------------------

resource "aws_cloudwatch_log_group" "notifier" {
  name              = "/aws/lambda/${var.project_name}-${var.environment}-notifier"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function" "notifier" {
  function_name    = "${var.project_name}-${var.environment}-notifier"
  filename         = data.archive_file.notifier.output_path
  source_code_hash = data.archive_file.notifier.output_base64sha256
  handler          = "lambda_function.lambda_handler"
  runtime          = var.lambda_runtime
  role             = var.lambda_notifier_role_arn
  timeout          = 30
  memory_size      = 256

  environment {
    variables = local.common_env
  }

  depends_on = [aws_cloudwatch_log_group.notifier]
}

resource "aws_lambda_permission" "allow_s3" {
  statement_id  = "AllowExecutionFromS3"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.notifier.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = var.offres_bucket_arn
}

# ---------------------------------------------------------------------
# API : toutes les routes du dashboard
# ---------------------------------------------------------------------

resource "aws_cloudwatch_log_group" "api" {
  name              = "/aws/lambda/${var.project_name}-${var.environment}-api"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function" "api" {
  function_name    = "${var.project_name}-${var.environment}-api"
  filename         = data.archive_file.api.output_path
  source_code_hash = data.archive_file.api.output_base64sha256
  handler          = "lambda_function.lambda_handler"
  runtime          = var.lambda_runtime
  role             = var.lambda_api_role_arn
  timeout          = 28 # API Gateway coupe à 29 s
  memory_size      = 256

  environment {
    variables = merge(local.common_env, {
      TABLE_CANDIDATURES   = var.table_candidatures_name
      TABLE_AUDIT          = var.table_audit_name
      COGNITO_USER_POOL_ID = var.cognito_user_pool_id
      CORS_ALLOWED_ORIGIN  = var.cors_allowed_origin
      DOCS_BUCKET          = var.documents_bucket_name
      OFFRES_BUCKET        = var.offres_bucket_name
      SENDER_EMAIL         = var.sender_email
      SES_SANDBOX_MODE     = tostring(var.ses_sandbox_mode)
    })
  }

  depends_on = [aws_cloudwatch_log_group.api]
}

# ---------------------------------------------------------------------
# Scheduler : digest hebdomadaire, rappels de date limite, clôture auto
# ---------------------------------------------------------------------

resource "aws_cloudwatch_log_group" "scheduler" {
  name              = "/aws/lambda/${var.project_name}-${var.environment}-scheduler"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function" "scheduler" {
  function_name    = "${var.project_name}-${var.environment}-scheduler"
  filename         = data.archive_file.scheduler.output_path
  source_code_hash = data.archive_file.scheduler.output_base64sha256
  handler          = "lambda_function.lambda_handler"
  runtime          = var.lambda_runtime
  role             = var.lambda_scheduler_role_arn
  timeout          = 300
  memory_size      = 256

  environment {
    variables = merge(local.common_env, {
      TABLE_CANDIDATURES = var.table_candidatures_name
      SENDER_EMAIL       = var.sender_email
      RAPPEL_JOURS       = tostring(var.rappel_jours)
    })
  }

  depends_on = [aws_cloudwatch_log_group.scheduler]
}
