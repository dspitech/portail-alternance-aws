"""Helpers partagés par les handlers de la Lambda API."""

import hashlib
import json
import os
import re
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key
from botocore.config import Config
from botocore.exceptions import ClientError

REGION = os.environ.get("AWS_REGION", "eu-west-3")

dynamodb = boto3.resource("dynamodb", region_name=REGION)
sns = boto3.client("sns", region_name=REGION)
cognito = boto3.client("cognito-idp", region_name=REGION)
ses = boto3.client("ses", region_name=REGION)
s3 = boto3.client(
    "s3",
    config=Config(region_name=REGION, signature_version="s3v4", s3={"addressing_style": "virtual"}),
)

T_OFFRES = dynamodb.Table(os.environ["TABLE_OFFRES"])
T_ETUDIANTS = dynamodb.Table(os.environ["TABLE_ETUDIANTS"])
T_CANDIDATURES = dynamodb.Table(os.environ["TABLE_CANDIDATURES"])
T_NOTIFICATIONS = dynamodb.Table(os.environ["TABLE_NOTIFICATIONS"])
T_AUDIT = dynamodb.Table(os.environ["TABLE_AUDIT"])

SNS_TOPIC_ARNS = json.loads(os.environ.get("SNS_TOPIC_ARNS", "{}"))
DOMAINES = list(SNS_TOPIC_ARNS.keys())
USER_POOL_ID = os.environ["COGNITO_USER_POOL_ID"]
DOCS_BUCKET = os.environ.get("DOCS_BUCKET", "")
OFFRES_BUCKET = os.environ.get("OFFRES_BUCKET", "")
SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "")
DASHBOARD_URL = os.environ.get("DASHBOARD_URL", "")
SES_SANDBOX = os.environ.get("SES_SANDBOX_MODE", "false").lower() == "true"

STATUTS_CANDIDATURE = ["Reçue", "Présélectionnée", "Entretien", "Acceptée", "Refusée"]
STATUTS_FINAUX = ("Acceptée", "Refusée")
STATUTS_OFFRE = ["Ouverte", "Clôturée"]
TYPES_DOCUMENTS = {
    "application/pdf": "pdf",
    "application/msword": "doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
}
TAILLE_MAX_DOCUMENT = 5 * 1024 * 1024

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

CORS_HEADERS = {
    "Access-Control-Allow-Origin": os.environ.get("CORS_ALLOWED_ORIGIN", "*"),
    "Access-Control-Allow-Headers": "Content-Type,Authorization",
    "Access-Control-Allow-Methods": "GET,POST,PUT,PATCH,DELETE,OPTIONS",
}


# ---------------------------------------------------------------------
# Réponses / erreurs
# ---------------------------------------------------------------------

class ApiError(Exception):
    def __init__(self, status_code, message):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def _decimal_default(obj):
    if isinstance(obj, Decimal):
        return int(obj) if obj % 1 == 0 else float(obj)
    raise TypeError


def response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {**CORS_HEADERS, "Content-Type": "application/json"},
        "body": json.dumps(body, default=_decimal_default, ensure_ascii=False),
    }


# ---------------------------------------------------------------------
# Dates
# ---------------------------------------------------------------------

def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def today_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def date_fr():
    return datetime.now(timezone.utc).strftime("%d/%m/%Y à %H:%M UTC")


# ---------------------------------------------------------------------
# Utilisateur courant (claims Cognito validés par API Gateway)
# ---------------------------------------------------------------------

def current_user(event):
    claims = (event.get("requestContext", {}).get("authorizer", {}) or {}).get("claims", {}) or {}
    raw = claims.get("cognito:groups", "") or ""
    if isinstance(raw, list):
        groupes = raw
    else:
        # Selon le cas : "Admins", "Admins,Etudiants" ou "[Admins Etudiants]"
        groupes = [g for g in re.split(r"[,\s\[\]]+", raw) if g]
    email = (claims.get("email") or claims.get("cognito:username") or "").lower()

    if "Admins" in groupes:
        role = "admin"
    elif "Recruteurs" in groupes:
        role = "recruteur"
    elif "Etudiants" in groupes:
        role = "etudiant"
    else:
        role = "inconnu"

    return {
        "email": email,
        "role": role,
        "groups": groupes,
        "is_admin": role == "admin",
        "is_staff": role in ("admin", "recruteur"),
    }


def require_admin(user):
    if not user["is_admin"]:
        raise ApiError(403, "Action réservée aux administrateurs")


def require_staff(user):
    if not user["is_staff"]:
        raise ApiError(403, "Action réservée aux administrateurs et recruteurs")


def require_etudiant(user):
    if user["role"] != "etudiant":
        raise ApiError(403, "Action réservée aux étudiants")


# ---------------------------------------------------------------------
# DynamoDB
# ---------------------------------------------------------------------

def scan_all(table, **kwargs):
    """Scan paginé : DynamoDB coupe chaque page à 1 Mo."""
    resp = table.scan(**kwargs)
    items = list(resp.get("Items", []))
    while "LastEvaluatedKey" in resp:
        resp = table.scan(ExclusiveStartKey=resp["LastEvaluatedKey"], **kwargs)
        items.extend(resp.get("Items", []))
    return items


def query_all(table, **kwargs):
    resp = table.query(**kwargs)
    items = list(resp.get("Items", []))
    while "LastEvaluatedKey" in resp:
        resp = table.query(ExclusiveStartKey=resp["LastEvaluatedKey"], **kwargs)
        items.extend(resp.get("Items", []))
    return items


def candidatures_de(email):
    return query_all(
        T_CANDIDATURES,
        IndexName="EtudiantEmail-index",
        KeyConditionExpression=Key("EtudiantEmail").eq(email),
    )


def get_offre(offre_id):
    offre = T_OFFRES.get_item(Key={"ID": offre_id}).get("Item")
    if not offre:
        raise ApiError(404, "Offre introuvable")
    return offre


def can_manage_offre(user, offre):
    """Admin : tout. Recruteur : uniquement ses propres offres."""
    if user["is_admin"]:
        return True
    return user["role"] == "recruteur" and offre.get("OwnerEmail", "") == user["email"]


def require_manage_offre(user, offre):
    if not can_manage_offre(user, offre):
        raise ApiError(403, "Vous ne pouvez gérer que vos propres offres")


# ---------------------------------------------------------------------
# Texte / validation
# ---------------------------------------------------------------------

def texte(body, key, max_len, required=False, label=None):
    val = body.get(key)
    val = val.strip() if isinstance(val, str) else ""
    if required and not val:
        raise ApiError(400, f"Le champ '{label or key}' est requis")
    if len(val) > max_len:
        raise ApiError(400, f"Le champ '{label or key}' dépasse {max_len} caractères")
    return val


def valider_email(email):
    email = (email or "").strip().lower()
    if not EMAIL_RE.match(email):
        raise ApiError(400, f"Email invalide : {email or '(vide)'}")
    return email


def valider_date(valeur):
    if not valeur:
        return ""
    try:
        datetime.strptime(valeur, "%Y-%m-%d")
    except ValueError:
        raise ApiError(400, "Date limite invalide (format AAAA-MM-JJ)")
    return valeur


def valider_url(valeur):
    if valeur and not re.match(r"^https?://", valeur):
        raise ApiError(400, "Le lien doit commencer par http:// ou https://")
    return valeur


def normaliser_domaines(domaines):
    """Valide, dédoublonne, et inscrit toujours l'étudiant au domaine 'General'."""
    for d in domaines:
        if d not in DOMAINES:
            raise ApiError(400, f"Domaine invalide : {d} (attendu : {DOMAINES})")
    res = list(dict.fromkeys(domaines))
    if "General" in DOMAINES and "General" not in res:
        res.append("General")
    return res


def hash_etudiant(email):
    return hashlib.sha256(email.lower().encode()).hexdigest()[:16]


# ---------------------------------------------------------------------
# Audit & historique des envois
# ---------------------------------------------------------------------

def audit(user, action, cible="", details=""):
    try:
        acteur = user["email"] if isinstance(user, dict) else str(user)
        T_AUDIT.put_item(
            Item={
                "ID": str(uuid.uuid4()),
                "Date": now_iso(),
                "Acteur": acteur,
                "Action": action,
                "Cible": cible,
                "Details": (details or "")[:500],
            }
        )
    except Exception as e:  # l'audit ne doit jamais casser une action métier
        print(f"Audit impossible : {e}")


def log_notification(type_, offre_id, titre, domaine, destinataires, acteur):
    try:
        T_NOTIFICATIONS.put_item(
            Item={
                "ID": str(uuid.uuid4()),
                "Date": now_iso(),
                "Type": type_,
                "OffreID": offre_id,
                "Titre": titre,
                "Domaine": domaine,
                "Destinataires": destinataires,
                "Acteur": acteur,
            }
        )
    except Exception as e:
        print(f"Log notification impossible : {e}")


# ---------------------------------------------------------------------
# SNS (alertes nouvelle offre) : abonnements par domaine
# ---------------------------------------------------------------------

def sns_subscribe(email, domaines):
    for d in domaines:
        arn = SNS_TOPIC_ARNS.get(d)
        if arn:
            sns.subscribe(TopicArn=arn, Protocol="email", Endpoint=email)


def sns_unsubscribe(email, domaines=None):
    """Désabonne l'email des topics (tous, ou seulement ceux de `domaines`).
    Les abonnements encore 'PendingConfirmation' ne sont pas désabonnables :
    ils expirent seuls après 3 jours."""
    for d, arn in SNS_TOPIC_ARNS.items():
        if domaines is not None and d not in domaines:
            continue
        paginator = sns.get_paginator("list_subscriptions_by_topic")
        for page in paginator.paginate(TopicArn=arn):
            for sub in page.get("Subscriptions", []):
                if sub.get("Endpoint", "").lower() == email and sub.get("SubscriptionArn", "").startswith("arn:"):
                    sns.unsubscribe(SubscriptionArn=sub["SubscriptionArn"])


def compter_etudiants(domaine):
    items = scan_all(T_ETUDIANTS, ProjectionExpression="Email, Domaines")
    return sum(1 for e in items if domaine in e.get("Domaines", []))


def notifier_offre(offre, acteur, rappel=False):
    """Publie l'offre sur le topic SNS de son domaine et journalise l'envoi."""
    topic = SNS_TOPIC_ARNS.get(offre["Domaine"])
    if not topic:
        raise ApiError(400, f"Aucun topic SNS pour le domaine {offre['Domaine']}")

    lien = offre.get("URL", "")
    if offre.get("FichierKey") and OFFRES_BUCKET:
        lien = s3.generate_presigned_url(
            "get_object", Params={"Bucket": OFFRES_BUCKET, "Key": offre["FichierKey"]}, ExpiresIn=3600
        )

    titre = offre.get("Titre") or offre.get("NomFichier", "")
    lignes = [
        "Rappel d'une offre disponible." if rappel else "Une nouvelle offre vient d'être publiée.",
        "",
        f"Poste : {titre}",
    ]
    if offre.get("Entreprise"):
        lignes.append(f"Entreprise : {offre['Entreprise']}")
    if offre.get("Lieu"):
        lignes.append(f"Lieu : {offre['Lieu']}")
    if offre.get("Rythme"):
        lignes.append(f"Rythme : {offre['Rythme']}")
    lignes.append(f"Domaine : {offre['Domaine']}")
    if offre.get("DateLimite"):
        lignes.append(f"Date limite : {offre['DateLimite']}")
    if lien:
        lignes += ["", f"Détail de l'offre : {lien}"]
    if DASHBOARD_URL:
        lignes += ["", f"Postulez depuis le dashboard : {DASHBOARD_URL}"]

    sujet = ("Rappel offre alternance : " if rappel else "Nouvelle offre alternance : ") + offre["Domaine"]
    sns.publish(TopicArn=topic, Message="\n".join(lignes), Subject=sujet)

    nb = compter_etudiants(offre["Domaine"])
    log_notification(
        "rappel_manuel" if rappel else "nouvelle_offre",
        offre["ID"], titre, offre["Domaine"], nb, acteur,
    )
    return nb


# ---------------------------------------------------------------------
# SES (emails HTML transactionnels)
# ---------------------------------------------------------------------

def _esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;"))


def email_html(titre, paragraphes, cta_label=None, cta_url=None):
    corps = "".join(f'<p style="margin:0 0 14px;line-height:1.55">{_esc(p)}</p>' for p in paragraphes)
    cta = ""
    if cta_label and cta_url:
        cta = (
            f'<p style="margin:22px 0"><a href="{_esc(cta_url)}" style="background:#10233F;color:#fff;'
            f'padding:11px 20px;text-decoration:none;font-weight:600">{_esc(cta_label)}</a></p>'
        )
    pied = ""
    if DASHBOARD_URL:
        pied = (
            f'<p style="margin:28px 0 0;font-size:12px;color:#5B6472">Vous recevez cet email car vous êtes inscrit(e) '
            f'sur le Portail Alternance. Gérez vos domaines suivis depuis votre profil : '
            f'<a href="{_esc(DASHBOARD_URL)}">{_esc(DASHBOARD_URL)}</a></p>'
        )
    return (
        '<div style="font-family:Arial,sans-serif;color:#1B1F23;max-width:560px;margin:auto;padding:24px">'
        f'<h2 style="margin:0 0 18px;color:#10233F">{_esc(titre)}</h2>{corps}{cta}{pied}</div>'
    )


def send_email(to, subject, html, text):
    if not SENDER_EMAIL:
        return False
    try:
        ses.send_email(
            Source=SENDER_EMAIL,
            Destination={"ToAddresses": [to]},
            Message={
                "Subject": {"Data": subject, "Charset": "UTF-8"},
                "Body": {
                    "Html": {"Data": html, "Charset": "UTF-8"},
                    "Text": {"Data": text, "Charset": "UTF-8"},
                },
            },
        )
        return True
    except ClientError as e:
        print(f"Envoi SES impossible vers {to} : {e}")
        return False


def ses_verifier_destinataire(email):
    """En sandbox SES, un destinataire doit être vérifié avant de recevoir des emails."""
    if not SES_SANDBOX:
        return
    try:
        ses.verify_email_identity(EmailAddress=email)
    except ClientError as e:
        print(f"Vérification SES impossible pour {email} : {e}")


# ---------------------------------------------------------------------
# Cognito
# ---------------------------------------------------------------------

def creer_compte(email, groupe):
    """Crée le compte Cognito (mot de passe temporaire envoyé par email) et l'ajoute au groupe.
    Retourne False si le compte existait déjà."""
    try:
        cognito.admin_create_user(
            UserPoolId=USER_POOL_ID,
            Username=email,
            UserAttributes=[
                {"Name": "email", "Value": email},
                {"Name": "email_verified", "Value": "true"},
            ],
            DesiredDeliveryMediums=["EMAIL"],
        )
    except cognito.exceptions.UsernameExistsException:
        return False
    cognito.admin_add_user_to_group(UserPoolId=USER_POOL_ID, Username=email, GroupName=groupe)
    return True
