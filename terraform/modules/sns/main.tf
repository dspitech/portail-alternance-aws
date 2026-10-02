# Un topic PAR DOMAINE : c'est ce qui permet un vrai ciblage (un étudiant
# "Cloud" ne reçoit que les offres Cloud). Les abonnements étudiants sont
# gérés dynamiquement par la Lambda API au moment de l'ajout/modification
# d'un étudiant (aws_sns_subscribe côté Python), pas par Terraform.
resource "aws_sns_topic" "par_domaine" {
  for_each = toset(var.domaines)
  name     = "${var.project_name}-${var.environment}-Alertes-${each.value}"
}

# L'admin est abonné à tous les topics pour supervision
resource "aws_sns_topic_subscription" "admin" {
  for_each  = aws_sns_topic.par_domaine
  topic_arn = each.value.arn
  protocol  = "email"
  endpoint  = var.admin_email
}
