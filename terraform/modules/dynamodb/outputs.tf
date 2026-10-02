output "table_offres_name" {
  value = aws_dynamodb_table.offres.name
}

output "table_offres_arn" {
  value = aws_dynamodb_table.offres.arn
}

output "table_etudiants_name" {
  value = aws_dynamodb_table.etudiants.name
}

output "table_etudiants_arn" {
  value = aws_dynamodb_table.etudiants.arn
}

output "table_candidatures_name" {
  value = aws_dynamodb_table.candidatures.name
}

output "table_candidatures_arn" {
  value = aws_dynamodb_table.candidatures.arn
}

output "table_notifications_name" {
  value = aws_dynamodb_table.notifications.name
}

output "table_notifications_arn" {
  value = aws_dynamodb_table.notifications.arn
}

output "table_audit_name" {
  value = aws_dynamodb_table.audit.name
}

output "table_audit_arn" {
  value = aws_dynamodb_table.audit.arn
}
