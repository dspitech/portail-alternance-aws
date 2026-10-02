"""Routes /me, /me/profile, /utilisateurs, /stats, /notifications, /audit."""

from collections import Counter
from datetime import datetime

from common import *  # noqa: F401,F403


# ---------------------------------------------------------------------
# /me
# ---------------------------------------------------------------------

def handle_me(method, rid, sub, body, user, event):
    if rid == "profile":
        return _profil(method, body, user)
    if method != "GET":
        raise ApiError(405, "Méthode non supportée sur /me")
    out = {**user, "domaines_disponibles": DOMAINES}
    if user["role"] == "etudiant":
        out["profil"] = T_ETUDIANTS.get_item(Key={"Email": user["email"]}).get("Item")
    return response(200, out)


def _profil(method, body, user):
    """L'étudiant gère lui-même ses domaines : met à jour ses abonnements SNS."""
    require_etudiant(user)
    if method != "PUT":
        raise ApiError(405, "Méthode non supportée sur /me/profile")

    actuel = T_ETUDIANTS.get_item(Key={"Email": user["email"]}).get("Item")
    if not actuel:
        raise ApiError(404, "Profil étudiant introuvable, contactez un administrateur")

    nouveaux = normaliser_domaines(body.get("domaines", actuel.get("Domaines", [])))
    anciens = actuel.get("Domaines", [])
    nom = texte(body, "nom", 100, label="nom") or actuel.get("Nom", "")

    ajoutes = [d for d in nouveaux if d not in anciens]
    retires = [d for d in anciens if d not in nouveaux]
    if ajoutes:
        sns_subscribe(user["email"], ajoutes)
    if retires:
        sns_unsubscribe(user["email"], retires)

    T_ETUDIANTS.update_item(
        Key={"Email": user["email"]},
        UpdateExpression="SET #n = :n, Domaines = :d",
        ExpressionAttributeNames={"#n": "Nom"},
        ExpressionAttributeValues={":n": nom, ":d": nouveaux},
    )
    return response(200, {"status": "profil mis à jour", "domaines": nouveaux})


# ---------------------------------------------------------------------
# /utilisateurs (comptes staff)
# ---------------------------------------------------------------------

def handle_utilisateurs(method, rid, sub, body, user, event):
    require_admin(user)
    if method != "POST" or rid:
        raise ApiError(405, "Méthode non supportée sur /utilisateurs")
    email = valider_email(body.get("email"))
    role = body.get("role")
    if role not in ("Admins", "Recruteurs"):
        raise ApiError(400, "Le champ 'role' doit valoir 'Admins' ou 'Recruteurs'")
    if not creer_compte(email, role):
        raise ApiError(409, "Un compte existe déjà avec cet email")
    ses_verifier_destinataire(email)
    audit(user, "utilisateur.creer", email, role)
    return response(201, {"email": email, "role": role, "status": "compte créé"})


# ---------------------------------------------------------------------
# /stats
# ---------------------------------------------------------------------

def _jours_entre(debut, fin):
    try:
        return (datetime.fromisoformat(fin) - datetime.fromisoformat(debut)).total_seconds() / 86400
    except (TypeError, ValueError):
        return None


def handle_stats(method, rid, sub, body, user, event):
    require_admin(user)
    if method != "GET":
        raise ApiError(405, "Méthode non supportée sur /stats")

    offres = scan_all(T_OFFRES)
    etudiants = scan_all(T_ETUDIANTS, ProjectionExpression="Email")
    cands = scan_all(T_CANDIDATURES)
    offres_map = {o["ID"]: o for o in offres}

    par_statut = Counter(c.get("Statut", "Reçue") for c in cands)
    par_domaine_cand = Counter(
        offres_map.get(c["OffreID"], {}).get("Domaine") or c.get("OffreDomaine") or "Inconnu" for c in cands
    )
    par_domaine_offres = Counter(o.get("Domaine", "General") for o in offres)

    decidees = [c for c in cands if c.get("Statut") in STATUTS_FINAUX]
    acceptees = sum(1 for c in decidees if c["Statut"] == "Acceptée")
    taux = round(100 * acceptees / len(decidees)) if decidees else None

    delais = [d for d in (_jours_entre(c.get("DateCandidature"), c.get("DateDecision")) for c in decidees)
              if d is not None]
    delai_moyen = round(sum(delais) / len(delais), 1) if delais else None

    avec_cand = {c["OffreID"] for c in cands}
    sans_cand = [
        {"ID": o["ID"], "Titre": o.get("Titre") or o.get("NomFichier", ""), "Domaine": o.get("Domaine", "")}
        for o in offres if o.get("Statut", "Ouverte") == "Ouverte" and o["ID"] not in avec_cand
    ]

    return response(200, {
        "total_offres": len(offres),
        "offres_ouvertes": sum(1 for o in offres if o.get("Statut", "Ouverte") == "Ouverte"),
        "total_etudiants": len(etudiants),
        "total_candidatures": len(cands),
        "candidatures_par_statut": dict(par_statut),
        "candidatures_par_domaine": dict(par_domaine_cand),
        "offres_par_domaine": dict(par_domaine_offres),
        "taux_acceptation": taux,
        "delai_moyen_jours": delai_moyen,
        "offres_sans_candidature": sans_cand[:20],
        "nb_offres_sans_candidature": len(sans_cand),
    })


# ---------------------------------------------------------------------
# /notifications, /audit
# ---------------------------------------------------------------------

def _limite(event, defaut=200):
    try:
        return max(1, min(int((event.get("queryStringParameters") or {}).get("limit", defaut)), 1000))
    except ValueError:
        return defaut


def handle_notifications(method, rid, sub, body, user, event):
    require_admin(user)
    if method != "GET":
        raise ApiError(405, "Méthode non supportée sur /notifications")
    items = sorted(scan_all(T_NOTIFICATIONS), key=lambda n: n.get("Date", ""), reverse=True)
    return response(200, items[: _limite(event)])


def handle_audit(method, rid, sub, body, user, event):
    require_admin(user)
    if method != "GET":
        raise ApiError(405, "Méthode non supportée sur /audit")
    items = sorted(scan_all(T_AUDIT), key=lambda a: a.get("Date", ""), reverse=True)
    return response(200, items[: _limite(event)])
