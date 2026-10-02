"""Routes /candidatures : liste, postuler, upload de documents, pipeline, notes."""

import re

from common import *  # noqa: F401,F403


def handle_candidatures(method, rid, sub, body, user, event):
    if method == "POST" and rid == "upload-url":
        return _upload_url(body, user)
    if method == "GET" and rid and sub == "documents":
        return _documents(rid, user)
    if method == "GET" and not rid:
        return _lister(user)
    if method == "POST" and not rid:
        return _postuler(body, user)
    if method == "PATCH" and rid:
        return _mettre_a_jour(rid, body, user)
    raise ApiError(405, "Méthode non supportée sur /candidatures")


# ---------------------------------------------------------------------
# Lecture
# ---------------------------------------------------------------------

def _lister(user):
    offres = {o["ID"]: o for o in scan_all(T_OFFRES)}

    if user["is_admin"]:
        cands = scan_all(T_CANDIDATURES)
    elif user["role"] == "recruteur":
        mes_offres = {oid for oid, o in offres.items() if o.get("OwnerEmail") == user["email"]}
        cands = [c for c in scan_all(T_CANDIDATURES) if c["OffreID"] in mes_offres]
    else:
        cands = candidatures_de(user["email"])

    out = []
    for c in cands:
        offre = offres.get(c["OffreID"], {})
        # Le titre est relu sur l'offre (reste à jour) ; l'instantané stocké sert si l'offre a été supprimée
        c["OffreTitre"] = offre.get("Titre") or offre.get("NomFichier") or c.get("OffreTitre", "(offre supprimée)")
        c["OffreDomaine"] = offre.get("Domaine") or c.get("OffreDomaine", "")
        c["OffreEntreprise"] = offre.get("Entreprise", "")
        c["HasCv"] = bool(c.pop("CvKey", ""))
        c["HasLettre"] = bool(c.pop("LettreKey", ""))
        if not user["is_staff"]:
            c.pop("NotesInternes", None)  # jamais visibles par l'étudiant
        out.append(c)

    out.sort(key=lambda c: c.get("DateCandidature", ""), reverse=True)
    return response(200, out)


# ---------------------------------------------------------------------
# Upload de documents (POST présigné direct vers S3)
# ---------------------------------------------------------------------

def _upload_url(body, user):
    require_etudiant(user)
    if not DOCS_BUCKET:
        raise ApiError(500, "Bucket de documents non configuré")

    type_doc = body.get("type")
    if type_doc not in ("cv", "lettre"):
        raise ApiError(400, "Le champ 'type' doit valoir 'cv' ou 'lettre'")
    content_type = body.get("contentType")
    if content_type not in TYPES_DOCUMENTS:
        raise ApiError(400, "Format refusé : PDF, DOC ou DOCX uniquement")

    ext = TYPES_DOCUMENTS[content_type]
    base = re.sub(r"[^A-Za-z0-9._-]", "_", (body.get("filename") or type_doc).rsplit(".", 1)[0])[:60] or type_doc
    key = f"documents/{hash_etudiant(user['email'])}/{uuid.uuid4().hex}-{base}.{ext}"

    post = s3.generate_presigned_post(
        Bucket=DOCS_BUCKET,
        Key=key,
        Fields={"Content-Type": content_type},
        Conditions=[
            {"Content-Type": content_type},
            ["content-length-range", 1, TAILLE_MAX_DOCUMENT],
        ],
        ExpiresIn=300,
    )
    return response(200, {"url": post["url"], "fields": post["fields"], "key": key})


def _documents(cand_id, user):
    cand = T_CANDIDATURES.get_item(Key={"ID": cand_id}).get("Item")
    if not cand:
        raise ApiError(404, "Candidature introuvable")

    if user["role"] == "etudiant":
        autorise = cand["EtudiantEmail"] == user["email"]
    elif user["is_admin"]:
        autorise = True
    else:
        offre = T_OFFRES.get_item(Key={"ID": cand["OffreID"]}).get("Item") or {}
        autorise = can_manage_offre(user, offre)
    if not autorise:
        raise ApiError(403, "Accès refusé à ces documents")

    def url(cle):
        if not cle:
            return None
        return s3.generate_presigned_url("get_object", Params={"Bucket": DOCS_BUCKET, "Key": cle}, ExpiresIn=300)

    return response(200, {"cv": url(cand.get("CvKey")), "lettre": url(cand.get("LettreKey")),
                          "message": cand.get("Message", "")})


# ---------------------------------------------------------------------
# Postuler
# ---------------------------------------------------------------------

def _postuler(body, user):
    require_etudiant(user)
    offre_id = body.get("offreId")
    if not offre_id:
        raise ApiError(400, "Le champ 'offreId' est requis")

    offre = get_offre(offre_id)
    if offre.get("Statut", "Ouverte") != "Ouverte":
        raise ApiError(409, "Cette offre est clôturée")
    if offre.get("DateLimite") and offre["DateLimite"] < today_iso():
        raise ApiError(409, "La date limite de cette offre est dépassée")
    if any(c["OffreID"] == offre_id for c in candidatures_de(user["email"])):
        raise ApiError(409, "Vous avez déjà postulé à cette offre")

    prefixe = f"documents/{hash_etudiant(user['email'])}/"
    cles = {}
    for champ, attr in (("cvKey", "CvKey"), ("lettreKey", "LettreKey")):
        cle = body.get(champ) or ""
        if cle and not cle.startswith(prefixe):
            raise ApiError(400, "Document invalide")  # empêche d'attacher le fichier d'un autre étudiant
        if cle:
            cles[attr] = cle

    profil = T_ETUDIANTS.get_item(Key={"Email": user["email"]}).get("Item") or {}
    cand = {
        "ID": str(uuid.uuid4()),
        "OffreID": offre_id,
        "OffreTitre": offre.get("Titre") or offre.get("NomFichier", ""),
        "OffreDomaine": offre.get("Domaine", ""),
        "EtudiantEmail": user["email"],
        "EtudiantNom": profil.get("Nom") or user["email"].split("@")[0],
        "Statut": "Reçue",
        "DateCandidature": now_iso(),
        "DateMaj": now_iso(),
        "Message": texte(body, "message", 2000, label="message"),
        **cles,
    }
    T_CANDIDATURES.put_item(Item=cand)
    return response(201, {"id": cand["ID"], "status": "candidature envoyée"})


# ---------------------------------------------------------------------
# Pipeline + notes internes
# ---------------------------------------------------------------------

def _mettre_a_jour(cand_id, body, user):
    require_staff(user)
    cand = T_CANDIDATURES.get_item(Key={"ID": cand_id}).get("Item")
    if not cand:
        raise ApiError(404, "Candidature introuvable")
    offre = T_OFFRES.get_item(Key={"ID": cand["OffreID"]}).get("Item") or {}
    if not (user["is_admin"] or can_manage_offre(user, offre)):
        raise ApiError(403, "Vous ne pouvez gérer que les candidatures de vos offres")

    sets, names, values, removes = ["#dm = :dm"], {"#dm": "DateMaj"}, {":dm": now_iso()}, []
    statut = body.get("statut")
    notes = body.get("notes")
    if statut is None and notes is None:
        raise ApiError(400, "Fournir 'statut' et/ou 'notes'")

    changement_statut = False
    if statut is not None:
        if statut not in STATUTS_CANDIDATURE:
            raise ApiError(400, f"Statut invalide (attendu : {STATUTS_CANDIDATURE})")
        changement_statut = statut != cand.get("Statut")
        sets.append("#s = :s")
        names["#s"] = "Statut"
        values[":s"] = statut
        if statut in STATUTS_FINAUX:
            sets.append("#dd = :dd")
            names["#dd"] = "DateDecision"
            values[":dd"] = now_iso()
        else:
            removes.append("#dd")
            names["#dd"] = "DateDecision"
    if notes is not None:
        sets.append("#n = :n")
        names["#n"] = "NotesInternes"
        values[":n"] = texte(body, "notes", 4000, label="notes")

    expr = "SET " + ", ".join(sets)
    if removes:
        expr += " REMOVE " + ", ".join(removes)
    T_CANDIDATURES.update_item(
        Key={"ID": cand_id},
        UpdateExpression=expr,
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=values,
    )

    if changement_statut:
        audit(user, "candidature.statut", cand_id, f"{cand.get('Statut')} -> {statut}")
        _prevenir_etudiant(cand, offre, statut, user)
    if notes is not None:
        audit(user, "candidature.notes", cand_id)
    return response(200, {"status": "mis à jour"})


def _prevenir_etudiant(cand, offre, statut, user):
    titre = offre.get("Titre") or offre.get("NomFichier") or cand.get("OffreTitre", "")
    phrase = {
        "Reçue": "Votre candidature est de nouveau en cours d'examen.",
        "Présélectionnée": "Bonne nouvelle : votre candidature a été présélectionnée.",
        "Entretien": "Vous êtes invité(e) à un entretien. L'équipe vous contactera pour fixer un créneau.",
        "Acceptée": "Félicitations, votre candidature a été acceptée !",
        "Refusée": "Nous avons le regret de vous informer que votre candidature n'a pas été retenue.",
    }[statut]
    sujet = f"Candidature « {titre} » : {statut}"
    html = email_html(
        f"Candidature : {statut}",
        [f"Offre : {titre}", phrase],
        "Voir mes candidatures", DASHBOARD_URL,
    )
    texte_brut = f"Offre : {titre}\n{phrase}\n\n{DASHBOARD_URL}"
    envoye = send_email(cand["EtudiantEmail"], sujet, html, texte_brut)
    log_notification("statut", cand["OffreID"], f"{titre} → {statut}", offre.get("Domaine", ""),
                     1 if envoye else 0, user["email"])
