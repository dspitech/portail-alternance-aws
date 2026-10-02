"""
Lambda planifiée (EventBridge). Deux tâches, choisies par event["task"] :

  digest  : résumé hebdomadaire, un email HTML par étudiant listant les offres
            ouvertes publiées ces 7 derniers jours dans ses domaines
  rappels : 1) clôture automatique des offres dont la date limite est passée
            2) rappel (email HTML) aux étudiants concernés qui n'ont pas encore
               postulé aux offres dont la date limite tombe dans RAPPEL_JOURS jours
"""

import html
import os
import uuid
from datetime import datetime, timedelta, timezone

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

REGION = os.environ.get("AWS_REGION", "eu-west-3")

dynamodb = boto3.resource("dynamodb", region_name=REGION)
ses = boto3.client("ses", region_name=REGION)

T_OFFRES = dynamodb.Table(os.environ["TABLE_OFFRES"])
T_ETUDIANTS = dynamodb.Table(os.environ["TABLE_ETUDIANTS"])
T_CANDIDATURES = dynamodb.Table(os.environ["TABLE_CANDIDATURES"])
T_NOTIFICATIONS = dynamodb.Table(os.environ["TABLE_NOTIFICATIONS"])
SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "")
DASHBOARD_URL = os.environ.get("DASHBOARD_URL", "")
RAPPEL_JOURS = int(os.environ.get("RAPPEL_JOURS", "3"))


def scan_all(table, **kwargs):
    resp = table.scan(**kwargs)
    items = list(resp.get("Items", []))
    while "LastEvaluatedKey" in resp:
        resp = table.scan(ExclusiveStartKey=resp["LastEvaluatedKey"], **kwargs)
        items.extend(resp.get("Items", []))
    return items


def titre_offre(o):
    return o.get("Titre") or o.get("NomFichier", "")


def send_email(to, subject, html_body, text_body):
    if not SENDER_EMAIL:
        return False
    try:
        ses.send_email(
            Source=SENDER_EMAIL,
            Destination={"ToAddresses": [to]},
            Message={
                "Subject": {"Data": subject, "Charset": "UTF-8"},
                "Body": {"Html": {"Data": html_body, "Charset": "UTF-8"},
                         "Text": {"Data": text_body, "Charset": "UTF-8"}},
            },
        )
        return True
    except ClientError as e:
        print(f"Envoi SES impossible vers {to} : {e}")
        return False


def log_notification(type_, offre_id, titre, domaine, destinataires):
    T_NOTIFICATIONS.put_item(
        Item={
            "ID": str(uuid.uuid4()),
            "Date": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "Type": type_,
            "OffreID": offre_id,
            "Titre": titre,
            "Domaine": domaine,
            "Destinataires": destinataires,
            "Acteur": "planificateur",
        }
    )


def page_html(titre, intro, lignes_html, cta_label):
    pied = (
        f'<p style="margin:28px 0 0;font-size:12px;color:#5B6472">Gérez vos domaines suivis depuis votre profil : '
        f'<a href="{html.escape(DASHBOARD_URL)}">{html.escape(DASHBOARD_URL)}</a></p>'
        if DASHBOARD_URL else ""
    )
    cta = (
        f'<p style="margin:22px 0"><a href="{html.escape(DASHBOARD_URL)}" style="background:#10233F;color:#fff;'
        f'padding:11px 20px;text-decoration:none;font-weight:600">{html.escape(cta_label)}</a></p>'
        if DASHBOARD_URL else ""
    )
    return (
        '<div style="font-family:Arial,sans-serif;color:#1B1F23;max-width:560px;margin:auto;padding:24px">'
        f'<h2 style="margin:0 0 14px;color:#10233F">{html.escape(titre)}</h2>'
        f'<p style="line-height:1.55">{html.escape(intro)}</p>{lignes_html}{cta}{pied}</div>'
    )


def ligne_offre_html(o):
    details = " · ".join(x for x in (o.get("Entreprise"), o.get("Lieu"), o.get("Domaine")) if x)
    limite = f' — date limite {html.escape(o["DateLimite"])}' if o.get("DateLimite") else ""
    return (
        f'<p style="margin:0 0 10px;padding:10px 12px;border-left:3px solid #0E7C6B;background:#F5F4EE">'
        f'<strong>{html.escape(titre_offre(o))}</strong><br>'
        f'<span style="color:#5B6472;font-size:13px">{html.escape(details)}{limite}</span></p>'
    )


def ligne_offre_txt(o):
    limite = f" (date limite {o['DateLimite']})" if o.get("DateLimite") else ""
    return f"- {titre_offre(o)} [{o.get('Domaine', '')}]{limite}"


# ---------------------------------------------------------------------
# Digest hebdomadaire
# ---------------------------------------------------------------------

def digest():
    depuis = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat(timespec="seconds")
    recentes = [o for o in scan_all(T_OFFRES)
                if o.get("Statut", "Ouverte") == "Ouverte" and o.get("CreeLe", "") >= depuis]
    if not recentes:
        print("Digest : aucune nouvelle offre cette semaine")
        return {"envoyes": 0}

    envoyes = 0
    for etu in scan_all(T_ETUDIANTS):
        mes_offres = [o for o in recentes if o.get("Domaine") in etu.get("Domaines", [])]
        if not mes_offres:
            continue
        titre = f"{len(mes_offres)} nouvelle(s) offre(s) cette semaine"
        corps_html = page_html(
            titre, f"Bonjour {etu.get('Nom', '')}, voici les offres publiées ces 7 derniers jours dans vos domaines.",
            "".join(ligne_offre_html(o) for o in mes_offres), "Voir les offres",
        )
        corps_txt = f"Bonjour {etu.get('Nom', '')},\n\n" + "\n".join(ligne_offre_txt(o) for o in mes_offres) \
            + f"\n\n{DASHBOARD_URL}"
        if send_email(etu["Email"], f"Portail Alternance : {titre}", corps_html, corps_txt):
            envoyes += 1

    log_notification("digest", "", f"{len(recentes)} offre(s) de la semaine", "Tous", envoyes)
    return {"envoyes": envoyes, "offres": len(recentes)}


# ---------------------------------------------------------------------
# Clôture automatique + rappels de date limite
# ---------------------------------------------------------------------

def rappels():
    aujourdhui = datetime.now(timezone.utc).date()
    limite_rappel = aujourdhui + timedelta(days=RAPPEL_JOURS)
    offres = scan_all(T_OFFRES)
    etudiants = scan_all(T_ETUDIANTS)

    clotures, rappelees, emails = 0, 0, 0
    for o in offres:
        if o.get("Statut", "Ouverte") != "Ouverte" or not o.get("DateLimite"):
            continue
        try:
            date_limite = datetime.strptime(o["DateLimite"], "%Y-%m-%d").date()
        except ValueError:
            continue

        if date_limite < aujourdhui:
            T_OFFRES.update_item(
                Key={"ID": o["ID"]},
                UpdateExpression="SET #s = :s",
                ExpressionAttributeNames={"#s": "Statut"},
                ExpressionAttributeValues={":s": "Clôturée"},
            )
            clotures += 1
            continue

        if date_limite <= limite_rappel and not o.get("RappelEnvoye"):
            deja = {c["EtudiantEmail"] for c in _candidatures_offre(o["ID"])}
            destinataires = [e for e in etudiants
                             if o.get("Domaine") in e.get("Domaines", []) and e["Email"] not in deja]
            envoyes = 0
            for etu in destinataires:
                corps_html = page_html(
                    "Dernier appel avant la date limite",
                    f"Bonjour {etu.get('Nom', '')}, cette offre se termine bientôt et vous n'avez pas encore postulé.",
                    ligne_offre_html(o), "Postuler",
                )
                corps_txt = (f"Bonjour {etu.get('Nom', '')},\n\nDate limite proche :\n{ligne_offre_txt(o)}\n\n"
                             f"{DASHBOARD_URL}")
                if send_email(etu["Email"], f"Date limite proche : {titre_offre(o)}", corps_html, corps_txt):
                    envoyes += 1
            emails += envoyes
            rappelees += 1
            T_OFFRES.update_item(
                Key={"ID": o["ID"]},
                UpdateExpression="SET RappelEnvoye = :t",
                ExpressionAttributeValues={":t": True},
            )
            log_notification("rappel_deadline", o["ID"], titre_offre(o), o.get("Domaine", ""), envoyes)

    return {"offres_cloturees": clotures, "offres_rappelees": rappelees, "emails": emails}


def _candidatures_offre(offre_id):
    resp = T_CANDIDATURES.query(IndexName="OffreID-index", KeyConditionExpression=Key("OffreID").eq(offre_id))
    items = list(resp.get("Items", []))
    while "LastEvaluatedKey" in resp:
        resp = T_CANDIDATURES.query(IndexName="OffreID-index", KeyConditionExpression=Key("OffreID").eq(offre_id),
                                    ExclusiveStartKey=resp["LastEvaluatedKey"])
        items.extend(resp.get("Items", []))
    return items


def lambda_handler(event, context):
    tache = (event or {}).get("task")
    if tache == "digest":
        return digest()
    if tache == "rappels":
        return rappels()
    raise ValueError(f"Tâche inconnue : {tache!r} (attendu : digest | rappels)")
