"""
Lambda déclenchée par un upload dans le bucket S3 des offres.

1. Détermine le domaine à partir du préfixe du nom de fichier
2. Enregistre l'offre dans DynamoDB (le fichier reste dans S3 : le dashboard
   génère une URL fraîche à la demande, les URLs présignées stockées expiraient)
3. Publie UNE fois sur le topic SNS du domaine : SNS distribue l'email aux
   étudiants abonnés à ce domaine (le ciblage vient des abonnements SNS).
4. Journalise l'envoi dans la table Notifications
"""

import json
import os
import uuid
from datetime import datetime, timezone
from urllib.parse import unquote_plus

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

REGION = os.environ.get("AWS_REGION", "eu-west-3")

s3_client = boto3.client(
    "s3", config=Config(region_name=REGION, signature_version="s3v4", s3={"addressing_style": "virtual"})
)
dynamodb = boto3.resource("dynamodb", region_name=REGION)
sns = boto3.client("sns", region_name=REGION)

T_OFFRES = dynamodb.Table(os.environ["TABLE_OFFRES"])
T_ETUDIANTS = dynamodb.Table(os.environ["TABLE_ETUDIANTS"])
T_NOTIFICATIONS = dynamodb.Table(os.environ["TABLE_NOTIFICATIONS"])
SNS_TOPIC_ARNS = json.loads(os.environ.get("SNS_TOPIC_ARNS", "{}"))  # { "Cloud": "arn:...", ... }
DASHBOARD_URL = os.environ.get("DASHBOARD_URL", "")

# Mapping préfixe de fichier -> domaine (voir README)
PREFIXES = {"Cloud": "Cloud", "Cyber": "Cyber", "Archi": "Archi", "Web": "Web"}


def nom_fichier(key: str) -> str:
    return key.rsplit("/", 1)[-1]


def domaine_depuis_cle(key: str) -> str:
    nom = nom_fichier(key)
    if "_" in nom:
        return PREFIXES.get(nom.split("_", 1)[0], "General")
    return "General"


def titre_depuis_cle(key: str) -> str:
    """Cloud_Architecte_AWS.pdf -> 'Architecte AWS'"""
    nom = os.path.splitext(nom_fichier(key))[0]
    if "_" in nom and nom.split("_", 1)[0] in PREFIXES:
        nom = nom.split("_", 1)[1]
    return nom.replace("_", " ").strip() or key


def scan_all(table, **kwargs):
    resp = table.scan(**kwargs)
    items = list(resp.get("Items", []))
    while "LastEvaluatedKey" in resp:
        resp = table.scan(ExclusiveStartKey=resp["LastEvaluatedKey"], **kwargs)
        items.extend(resp.get("Items", []))
    return items


def lambda_handler(event, context):
    resultats = []
    for record in event.get("Records", []):
        bucket = record["s3"]["bucket"]["name"]
        key = unquote_plus(record["s3"]["object"]["key"])  # S3 encode les espaces en '+'
        resultats.append(_traiter(bucket, key))
    return {"status": "success", "resultats": resultats}


def _traiter(bucket: str, key: str) -> dict:
    domaine = domaine_depuis_cle(key)
    titre = titre_depuis_cle(key)
    maintenant = datetime.now(timezone.utc)

    try:
        url_temporaire = s3_client.generate_presigned_url(
            "get_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=3600
        )
    except ClientError as e:
        print(f"Erreur génération URL présignée : {e}")
        return {"key": key, "status": "error", "reason": str(e)}

    offre_id = str(uuid.uuid4())
    T_OFFRES.put_item(
        Item={
            "ID": offre_id,
            "Titre": titre,
            "NomFichier": key,
            "FichierKey": key,
            "FichierBucket": bucket,
            "Entreprise": "",
            "Lieu": "",
            "Duree": "",
            "Rythme": "",
            "Description": "",
            "URL": "",
            "DateLimite": "",
            "Statut": "Ouverte",
            "Domaine": domaine,
            "CreeLe": maintenant.isoformat(timespec="seconds"),
            "DatePublication": maintenant.strftime("%d/%m/%Y à %H:%M UTC"),
            "Source": "s3-upload",
            "OwnerEmail": "",
        }
    )

    etudiants = scan_all(T_ETUDIANTS, ProjectionExpression="Email, Domaines")
    nb = sum(1 for e in etudiants if domaine in e.get("Domaines", []))

    topic_arn = SNS_TOPIC_ARNS.get(domaine)
    if not topic_arn:
        print(f"Aucun topic SNS pour le domaine {domaine}, notification non envoyée")
        return {"key": key, "offre_id": offre_id, "notified": False}

    corps = (
        "Une nouvelle offre vient d'être publiée.\n\n"
        f"Poste : {titre}\n"
        f"Domaine : {domaine}\n"
        f"Publiée le : {maintenant.strftime('%d/%m/%Y à %H:%M UTC')}\n\n"
        f"Fichier de l'offre (lien valable 1 h) :\n{url_temporaire}\n"
    )
    if DASHBOARD_URL:
        corps += f"\nPostulez depuis le dashboard : {DASHBOARD_URL}\n"
    sns.publish(TopicArn=topic_arn, Message=corps, Subject=f"Nouvelle offre alternance : {domaine}")

    T_NOTIFICATIONS.put_item(
        Item={
            "ID": str(uuid.uuid4()),
            "Date": maintenant.isoformat(timespec="seconds"),
            "Type": "nouvelle_offre",
            "OffreID": offre_id,
            "Titre": titre,
            "Domaine": domaine,
            "Destinataires": nb,
            "Acteur": "upload S3",
        }
    )
    return {"key": key, "offre_id": offre_id, "domaine": domaine, "notified": True, "destinataires": nb}
