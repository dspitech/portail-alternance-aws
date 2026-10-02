# Deux tâches planifiées qui appellent la Lambda "scheduler" :
#  - digest  : résumé hebdomadaire des nouvelles offres par étudiant
#  - rappels : rappel de date limite + clôture automatique des offres expirées

locals {
  taches = {
    digest  = var.digest_cron
    rappels = var.rappels_cron
  }
}

resource "aws_cloudwatch_event_rule" "tache" {
  for_each            = local.taches
  name                = "${var.project_name}-${var.environment}-${each.key}"
  description         = "Tâche planifiée : ${each.key}"
  schedule_expression = each.value
}

resource "aws_cloudwatch_event_target" "tache" {
  for_each = local.taches
  rule     = aws_cloudwatch_event_rule.tache[each.key].name
  arn      = var.scheduler_function_arn
  input    = jsonencode({ task = each.key })
}

resource "aws_lambda_permission" "tache" {
  for_each      = local.taches
  statement_id  = "AllowEventBridge-${each.key}"
  action        = "lambda:InvokeFunction"
  function_name = var.scheduler_function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.tache[each.key].arn
}
