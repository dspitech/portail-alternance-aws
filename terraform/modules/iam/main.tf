data "aws_iam_policy_document" "lambda_trust" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

# =====================================================================
# Lambda "notifier" (déclenchée par un upload S3)
# =====================================================================

resource "aws_iam_role" "lambda_notifier" {
  name               = "${var.project_name}-${var.environment}-lambda-notifier-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_trust.json
}

resource "aws_iam_role_policy_attachment" "notifier_basic_logs" {
  role       = aws_iam_role.lambda_notifier.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "lambda_notifier_inline" {
  statement {
    sid       = "LireOffresS3"
    effect    = "Allow"
    actions   = ["s3:GetObject"]
    resources = ["${var.offres_bucket_arn}/*"]
  }

  statement {
    sid       = "DynamoDB"
    effect    = "Allow"
    actions   = ["dynamodb:PutItem", "dynamodb:Scan"]
    resources = [var.table_offres_arn, var.table_etudiants_arn, var.table_notifications_arn]
  }

  statement {
    sid       = "PublierSNS"
    effect    = "Allow"
    actions   = ["sns:Publish"]
    resources = var.sns_topic_arns
  }
}

resource "aws_iam_role_policy" "lambda_notifier_inline" {
  name   = "${var.project_name}-${var.environment}-lambda-notifier-policy"
  role   = aws_iam_role.lambda_notifier.id
  policy = data.aws_iam_policy_document.lambda_notifier_inline.json
}

# =====================================================================
# Lambda "api" (derrière API Gateway)
# =====================================================================

resource "aws_iam_role" "lambda_api" {
  name               = "${var.project_name}-${var.environment}-lambda-api-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_trust.json
}

resource "aws_iam_role_policy_attachment" "api_basic_logs" {
  role       = aws_iam_role.lambda_api.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "lambda_api_inline" {
  statement {
    sid    = "CRUDDynamoDB"
    effect = "Allow"
    actions = [
      "dynamodb:PutItem",
      "dynamodb:GetItem",
      "dynamodb:UpdateItem",
      "dynamodb:DeleteItem",
      "dynamodb:Scan",
      "dynamodb:Query"
    ]
    resources = [
      var.table_offres_arn,
      var.table_etudiants_arn,
      var.table_candidatures_arn,
      "${var.table_candidatures_arn}/index/*",
      var.table_notifications_arn,
      var.table_audit_arn,
    ]
  }

  statement {
    sid       = "PublierSNS"
    effect    = "Allow"
    actions   = ["sns:Publish"]
    resources = var.sns_topic_arns
  }

  statement {
    sid    = "GererAbonnementsSNS"
    effect = "Allow"
    actions = [
      "sns:Subscribe",
      "sns:Unsubscribe",
      "sns:ListSubscriptionsByTopic"
    ]
    resources = var.sns_topic_arns
  }

  statement {
    sid    = "GererUtilisateursCognito"
    effect = "Allow"
    actions = [
      "cognito-idp:AdminCreateUser",
      "cognito-idp:AdminAddUserToGroup",
      "cognito-idp:AdminDeleteUser",
      "cognito-idp:AdminGetUser"
    ]
    resources = [var.cognito_user_pool_arn]
  }

  statement {
    sid       = "DocumentsCandidatures"
    effect    = "Allow"
    actions   = ["s3:PutObject", "s3:GetObject", "s3:DeleteObject"]
    resources = ["${var.documents_bucket_arn}/*"]
  }

  statement {
    sid       = "LireFichiersOffres"
    effect    = "Allow"
    actions   = ["s3:GetObject"]
    resources = ["${var.offres_bucket_arn}/*"]
  }

  statement {
    sid       = "EmailsSES"
    effect    = "Allow"
    actions   = ["ses:SendEmail"]
    resources = [var.ses_identity_arn]
  }

  # Vérification automatique des destinataires tant que SES est en sandbox
  statement {
    sid       = "VerifierDestinatairesSES"
    effect    = "Allow"
    actions   = ["ses:VerifyEmailIdentity"]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "lambda_api_inline" {
  name   = "${var.project_name}-${var.environment}-lambda-api-policy"
  role   = aws_iam_role.lambda_api.id
  policy = data.aws_iam_policy_document.lambda_api_inline.json
}

# =====================================================================
# Lambda "scheduler" (digest hebdo + rappels de date limite)
# =====================================================================

resource "aws_iam_role" "lambda_scheduler" {
  name               = "${var.project_name}-${var.environment}-lambda-scheduler-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_trust.json
}

resource "aws_iam_role_policy_attachment" "scheduler_basic_logs" {
  role       = aws_iam_role.lambda_scheduler.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "lambda_scheduler_inline" {
  statement {
    sid    = "DynamoDB"
    effect = "Allow"
    actions = [
      "dynamodb:Scan",
      "dynamodb:Query",
      "dynamodb:UpdateItem",
      "dynamodb:PutItem"
    ]
    resources = [
      var.table_offres_arn,
      var.table_etudiants_arn,
      var.table_candidatures_arn,
      "${var.table_candidatures_arn}/index/*",
      var.table_notifications_arn,
    ]
  }

  statement {
    sid       = "EmailsSES"
    effect    = "Allow"
    actions   = ["ses:SendEmail"]
    resources = [var.ses_identity_arn]
  }
}

resource "aws_iam_role_policy" "lambda_scheduler_inline" {
  name   = "${var.project_name}-${var.environment}-lambda-scheduler-policy"
  role   = aws_iam_role.lambda_scheduler.id
  policy = data.aws_iam_policy_document.lambda_scheduler_inline.json
}
