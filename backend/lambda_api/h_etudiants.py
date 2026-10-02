"""Routes /etudiants : liste, ajout, import en masse, suppression (purge RGPD)."""

from common import *  # noqa: F401,F403

MAX_IMPORT = 50  # 1 étudiant = plusieurs appels AWS ; on reste sous les 29 s d'API Gateway


def handle_etudiants(method, rid, sub, body, user, event):
    require_admin(user)

    if method == "GET" and not rid:
        items = scan_all(T_ETUDIANTS)
        items.sort(key=lambda e: e.get("Nom", "").lower())
        return response(200, items)
    if method == "POST" and rid == "import":
        return _importer(body, user)
    if method == "POST" and not rid:
        return _ajouter_route(body, user)
    if method == "DELETE" and rid:
        return _supprimer(rid, user)
    raise ApiError(405, "Méthode non supportée sur /etudiants")


def ajouter_etudiant(email, nom, domaines):
    """Écrit DynamoDB, abonne aux topics SNS, crée le compte Cognito. Retourne l'item."""
    email = valider_email(email)
    domaines = normaliser_domaines(domaines or [])
    nom = (nom or "").strip()[:100] or email.split("@")[0].replace(".", " ").title()

    item = {"Email": email, "Nom": nom, "Domaines": domaines, "DateAjout": now_iso()}
    T_ETUDIANTS.put_item(Item=item)
    sns_subscribe(email, domaines)
    creer_compte(email, "Etudiants")
    ses_verifier_destinataire(email)
    return item


def _ajouter_route(body, user):
    item = ajouter_etudiant(body.get("email"), body.get("nom"), body.get("domaines"))
    audit(user, "etudiant.ajouter", item["Email"], ",".join(item["Domaines"]))
    return response(201, {"email": item["Email"], "status": "ajouté"})


def _importer(body, user):
    lignes = body.get("etudiants")
    if not isinstance(lignes, list) or not lignes:
        raise ApiError(400, "Le champ 'etudiants' doit être une liste non vide")
    if len(lignes) > MAX_IMPORT:
        raise ApiError(400, f"Maximum {MAX_IMPORT} étudiants par requête")

    crees, erreurs = 0, []
    for ligne in lignes:
        email = (ligne or {}).get("email", "")
        try:
            ajouter_etudiant(email, ligne.get("nom"), ligne.get("domaines"))
            crees += 1
        except ApiError as e:
            erreurs.append({"email": email, "erreur": e.message})
        except ClientError as e:
            print(f"Import {email} : {e}")
            erreurs.append({"email": email, "erreur": "Erreur AWS"})

    audit(user, "etudiant.importer", f"{crees} créés", f"{len(erreurs)} erreurs")
    return response(200, {"crees": crees, "erreurs": erreurs})


def _supprimer(email, user):
    """Suppression RGPD : étudiant + candidatures + documents + abonnements + compte."""
    email = valider_email(email)

    nb_cand = 0
    for cand in candidatures_de(email):
        for cle in ("CvKey", "LettreKey"):
            if cand.get(cle) and DOCS_BUCKET:
                s3.delete_object(Bucket=DOCS_BUCKET, Key=cand[cle])
        T_CANDIDATURES.delete_item(Key={"ID": cand["ID"]})
        nb_cand += 1

    sns_unsubscribe(email)
    T_ETUDIANTS.delete_item(Key={"Email": email})
    try:
        cognito.admin_delete_user(UserPoolId=USER_POOL_ID, Username=email)
    except cognito.exceptions.UserNotFoundException:
        pass

    audit(user, "etudiant.supprimer", email, f"{nb_cand} candidature(s) purgée(s)")
    return response(200, {"status": "supprimé", "candidatures_supprimees": nb_cand})
