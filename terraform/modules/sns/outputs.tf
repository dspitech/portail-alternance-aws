output "topic_arns_par_domaine" {
  description = "Map { domaine = topic_arn }"
  value       = { for d, t in aws_sns_topic.par_domaine : d => t.arn }
}
