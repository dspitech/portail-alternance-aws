output "lambda_notifier_role_arn" {
  value = aws_iam_role.lambda_notifier.arn
}

output "lambda_api_role_arn" {
  value = aws_iam_role.lambda_api.arn
}

output "lambda_scheduler_role_arn" {
  value = aws_iam_role.lambda_scheduler.arn
}
