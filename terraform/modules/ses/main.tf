# Identité expéditrice SES. AWS envoie un email de vérification à cette adresse :
# il faut cliquer sur le lien avant que les emails (statuts, digest, rappels) partent.
#
# Nouveau compte SES = mode "sandbox" : les destinataires doivent aussi être
# vérifiés (géré automatiquement par l'API tant que ses_sandbox_mode = true).
# Pour un usage réel, demander la sortie de sandbox dans la console SES.

resource "aws_ses_email_identity" "sender" {
  email = var.sender_email
}
