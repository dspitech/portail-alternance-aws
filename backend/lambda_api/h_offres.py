"""Routes /offres : liste, création, modification, suppression, fichier, notification."""

from collections import Counter

from common import *  # noqa: F401,F403

CHAMPS_MODIFIABLES = {
    "titre": "Titre",
    "entreprise": "Entreprise",
    "lieu": "Lieu",
    "duree": "Duree",
    "rythme": "Rythme",
    "description": "Description",
    "url": "URL",
    "date_limite": "DateLimite",
    "statut": "Statut",
    "domaine": "Domaine",
}


def handle_offres(method, rid, sub, body, user, event):
    if rid and sub == "fichier" and method == "GET":
        return _fichier(rid)
    if not rid and method == "GET":
        return _lister(user)
    if not rid and method == "POST":
        return _creer(body, user)
    if rid and method == "PATCH":
        return _modifier(rid, body, user)
    if rid and method == "DELETE":
        return _supprimer(rid, user)
    raise ApiError(405, "Méthode non supportée sur /offres")


def _lister(user):
    offres = scan_all(T_OFFRES)
    if user["role"] == "recruteur":
        offres = [o for o in offres if o.get("OwnerEmail") == user["email"]]

    if user["is_staff"]:
        nb = Counter(c["OffreID"] for c in scan_all(T_CANDIDATURES, ProjectionExpression="OffreID"))
        for o in offres:
            o["NbCandidatures"] = nb.get(o["ID"], 0)
    elif user["role"] == "etudiant":
        deja = {c["OffreID"] for c in candidatures_de(user["email"])}
        for o in offres:
            o["DejaPostule"] = o["ID"] in deja

    offres.sort(key=lambda o: o.get("CreeLe", ""), reverse=True)
    return response(200, offres)


def _valider_champs(body, creation):
    """Retourne le dict {attribut DynamoDB: valeur} des champs présents (et valides)."""
    out = {}
    if creation or "titre" in body:
        out["Titre"] = texte(body, "titre", 150, required=True, label="titre")
    if creation or "domaine" in body:
        domaine = body.get("domaine")
        if domaine not in DOMAINES:
            raise ApiError(400, f"Domaine invalide, attendu un de : {DOMAINES}")
        out["Domaine"] = domaine
    for cle, attr, max_len in (
        ("entreprise", "Entreprise", 100),
        ("lieu", "Lieu", 100),
        ("duree", "Duree", 50),
        ("rythme", "Rythme", 80),
        ("description", "Description", 4000),
    ):
        if cle in body:
            out[attr] = texte(body, cle, max_len, label=cle)
    if "url" in body:
        out["URL"] = valider_url(texte(body, "url", 500, label="url"))
    if "date_limite" in body:
        out["DateLimite"] = valider_date(texte(body, "date_limite", 10, label="date limite"))
    if "statut" in body:
        if body["statut"] not in STATUTS_OFFRE:
            raise ApiError(400, f"Statut d'offre invalide (attendu : {STATUTS_OFFRE})")
        out["Statut"] = body["statut"]
    return out


def _creer(body, user):
    require_staff(user)
    champs = _valider_champs(body, creation=True)

    offre = {
        "ID": str(uuid.uuid4()),
        "NomFichier": champs["Titre"],  # compatibilité avec les offres issues d'un upload S3
        "Entreprise": "",
        "Lieu": "",
        "Duree": "",
        "Rythme": "",
        "Description": "",
        "URL": "",
        "DateLimite": "",
        "Statut": "Ouverte",
        "CreeLe": now_iso(),
        "DatePublication": date_fr(),
        "Source": "dashboard",
        "OwnerEmail": user["email"],
        **champs,
    }
    T_OFFRES.put_item(Item=offre)
    audit(user, "offre.creer", offre["ID"], offre["Titre"])

    nb = None
    if body.get("notifier", True):
        nb = notifier_offre(offre, user["email"])
    return response(201, {"id": offre["ID"], "status": "créée", "notifies": nb})


def _modifier(offre_id, body, user):
    offre = get_offre(offre_id)
    require_manage_offre(user, offre)
    champs = _valider_champs(body, creation=False)
    if not champs:
        raise ApiError(400, "Aucun champ à modifier")

    sets, names, values = [], {}, {}
    for i, (attr, val) in enumerate(champs.items()):
        names[f"#a{i}"] = attr
        values[f":v{i}"] = val
        sets.append(f"#a{i} = :v{i}")
    expr = "SET " + ", ".join(sets)

    # Nouvelle échéance ou réouverture : le rappel de date limite doit pouvoir repartir
    if "DateLimite" in champs or champs.get("Statut") == "Ouverte":
        names["#r"] = "RappelEnvoye"
        expr += " REMOVE #r"

    T_OFFRES.update_item(
        Key={"ID": offre_id},
        UpdateExpression=expr,
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=values,
    )
    audit(user, "offre.modifier", offre_id, ", ".join(sorted(champs.keys())))
    return response(200, {"status": "mise à jour"})


def _supprimer(offre_id, user):
    offre = get_offre(offre_id)
    require_manage_offre(user, offre)
    T_OFFRES.delete_item(Key={"ID": offre_id})
    audit(user, "offre.supprimer", offre_id, offre.get("Titre") or offre.get("NomFichier", ""))
    return response(200, {"status": "supprimée"})


def _fichier(offre_id):
    """URL fraîche vers le fichier de l'offre (les URLs présignées stockées expiraient)."""
    offre = get_offre(offre_id)
    if offre.get("FichierKey") and OFFRES_BUCKET:
        url = s3.generate_presigned_url(
            "get_object", Params={"Bucket": OFFRES_BUCKET, "Key": offre["FichierKey"]}, ExpiresIn=300
        )
        return response(200, {"url": url})
    if offre.get("URL"):
        return response(200, {"url": offre["URL"]})
    raise ApiError(404, "Aucun fichier ni lien pour cette offre")


def handle_notify(method, body, user):
    if method != "POST":
        raise ApiError(405, "Méthode non supportée sur /notify")
    require_staff(user)
    offre_id = body.get("offreId")
    if not offre_id:
        raise ApiError(400, "Le champ 'offreId' est requis")
    offre = get_offre(offre_id)
    require_manage_offre(user, offre)
    nb = notifier_offre(offre, user["email"], rappel=True)
    audit(user, "offre.renotifier", offre_id, offre.get("Domaine", ""))
    return response(200, {"status": "notification envoyée", "domaine": offre["Domaine"], "destinataires": nb})
