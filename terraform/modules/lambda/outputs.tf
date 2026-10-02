output "notifier_function_name" {
  value = aws_lambda_function.notifier.function_name
}

output "notifier_function_arn" {
  value = aws_lambda_function.notifier.arn
}

output "api_function_name" {
  value = aws_lambda_function.api.function_name
}

output "api_function_arn" {
  value = aws_lambda_function.api.arn
}

output "api_function_invoke_arn" {
  value = aws_lambda_function.api.invoke_arn
}

output "scheduler_function_name" {
  value = aws_lambda_function.scheduler.function_name
}

output "scheduler_function_arn" {
  value = aws_lambda_function.scheduler.arn
}
