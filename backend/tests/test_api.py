import json
from datetime import datetime, timedelta, timezone

import boto3

from conftest import sent_emails

OFFRE = {"titre": "Développeur Cloud", "domaine": "Cloud", "entreprise": "Acme", "lieu": "Paris",
         "duree": "12 mois", "rythme": "3j/2j", "date_limite": "2099-12-31"}


def creer_offre(api, role="admin", **extra):
    s, b = api.call("POST", "offres", {**OFFRE, **extra}, role=role)
    assert s == 201, b
    return b["id"]


def ajouter_etudiant(api, email="jean.dupont@ecole.com", **extra):
    s, b = api.call("POST", "etudiants", {"email": email, "domaines": ["Cloud"], **extra})
    assert s == 201, b


# ------------------------------------------------------------------ droits
def test_roles_et_droits(api):
    assert api.call("GET", "offres", role="aucun")[0] == 403
    assert api.call("GET", "me", role="aucun")[0] == 200
    assert api.call("POST", "offres", OFFRE, role="etudiant")[0] == 403
    assert api.call("GET", "etudiants", role="recruteur")[0] == 403
    assert api.call("GET", "stats", role="etudiant")[0] == 403
    assert api.call("GET", "audit", role="recruteur")[0] == 403
    assert api.call("GET", "inconnu")[0] == 404


def test_groupes_cognito_formats(api):
    from common import current_user
    for raw in ("Admins", "Admins,Etudiants", "[Admins Etudiants]"):
        ev = {"requestContext": {"authorizer": {"claims": {"email": "a@b.c", "cognito:groups": raw}}}}
        assert current_user(ev)["role"] == "admin", raw


# ------------------------------------------------------------------ offres
def test_offre_structuree_notifiee_et_journalisee(api, aws):
    oid = creer_offre(api)
    offres = api.call("GET", "offres")[1]
    assert offres[0]["Entreprise"] == "Acme" and offres[0]["Statut"] == "Ouverte"
    assert offres[0]["NbCandidatures"] == 0
    notifs = api.call("GET", "notifications")[1]
    assert notifs[0]["Type"] == "nouvelle_offre" and notifs[0]["OffreID"] == oid


def test_offre_sans_notification(api):
    creer_offre(api, notifier=False)
    assert api.call("GET", "notifications")[1] == []


def test_validation_offre(api):
    assert api.call("POST", "offres", {**OFFRE, "domaine": "Nope"})[0] == 400
    assert api.call("POST", "offres", {**OFFRE, "date_limite": "31/12/2099"})[0] == 400
    assert api.call("POST", "offres", {**OFFRE, "url": "javascript:alert(1)"})[0] == 400
    assert api.call("POST", "offres", {**OFFRE, "titre": ""})[0] == 400
    assert api.call("POST", "offres", {**OFFRE, "titre": "x" * 200})[0] == 400


def test_recruteur_isole(api):
    oid_admin = creer_offre(api)
    oid_rh = creer_offre(api, role="recruteur")
    ids = [o["ID"] for o in api.call("GET", "offres", role="recruteur")[1]]
    assert ids == [oid_rh]
    assert api.call("PATCH", f"offres/{oid_admin}", {"statut": "Clôturée"}, role="recruteur")[0] == 403
    assert api.call("DELETE", f"offres/{oid_admin}", role="recruteur")[0] == 403
    assert api.call("POST", "notify", {"offreId": oid_admin}, role="recruteur")[0] == 403
    assert api.call("PATCH", f"offres/{oid_rh}", {"statut": "Clôturée"}, role="recruteur")[0] == 200


def test_modifier_et_supprimer_offre(api):
    oid = creer_offre(api)
    assert api.call("PATCH", f"offres/{oid}", {})[0] == 400
    assert api.call("PATCH", f"offres/{oid}", {"lieu": "Lyon", "statut": "Clôturée"})[0] == 200
    o = api.call("GET", "offres")[1][0]
    assert o["Lieu"] == "Lyon" and o["Statut"] == "Clôturée"
    assert api.call("DELETE", f"offres/{oid}")[0] == 200
    assert api.call("GET", "offres")[1] == []


def test_fichier_offre_url_fraiche(api, aws):
    aws["s3"].put_object(Bucket="offres", Key="Cloud_X.pdf", Body=b"x")
    aws["ddb"].Table("Offres").put_item(Item={"ID": "o1", "Titre": "X", "Domaine": "Cloud", "FichierKey": "Cloud_X.pdf"})
    s, b = api.call("GET", "offres/o1/fichier", role="etudiant")
    assert s == 200 and "Cloud_X.pdf" in b["url"]


# ------------------------------------------------------------------ étudiants
def test_ajout_etudiant(api, aws):
    ajouter_etudiant(api)
    etu = api.call("GET", "etudiants")[1][0]
    assert etu["Nom"] == "Jean Dupont"
    assert set(etu["Domaines"]) == {"Cloud", "General"}  # General ajouté d'office
    users = aws["cog"].list_users(UserPoolId=aws["pool"])["Users"]
    assert [u["Username"] for u in users] == ["jean.dupont@ecole.com"]
    assert api.call("POST", "etudiants", {"email": "pas-un-email", "domaines": []})[0] == 400
    assert api.call("POST", "etudiants", {"email": "a@b.co", "domaines": ["Nope"]})[0] == 400
    ajouter_etudiant(api)  # doublon : idempotent


def test_import_masse(api):
    lignes = [{"email": "a@ecole.com", "domaines": ["Cloud"]},
              {"email": "cassé", "domaines": []},
              {"email": "b@ecole.com", "nom": "Bob", "domaines": ["Cyber"]}]
    s, b = api.call("POST", "etudiants/import", {"etudiants": lignes})
    assert s == 200 and b["crees"] == 2 and b["erreurs"][0]["email"] == "cassé"
    assert api.call("POST", "etudiants/import", {"etudiants": [{"email": f"{i}@x.co"} for i in range(51)]})[0] == 400
    assert api.call("POST", "etudiants/import", {"etudiants": []})[0] == 400


def test_profil_etudiant(api):
    ajouter_etudiant(api)
    s, b = api.call("PUT", "me/profile", {"nom": "Jean D.", "domaines": ["Cyber"]}, role="etudiant")
    assert s == 200 and set(b["domaines"]) == {"Cyber", "General"}
    me = api.call("GET", "me", role="etudiant")[1]
    assert me["profil"]["Nom"] == "Jean D." and "Cloud" not in me["profil"]["Domaines"]
    assert api.call("PUT", "me/profile", {"domaines": ["Nope"]}, role="etudiant")[0] == 400
    assert api.call("PUT", "me/profile", {"domaines": []}, role="admin")[0] == 403


def test_creation_compte_staff(api, aws):
    assert api.call("POST", "utilisateurs", {"email": "rh@acme.com", "role": "Recruteurs"})[0] == 201
    assert api.call("POST", "utilisateurs", {"email": "rh@acme.com", "role": "Recruteurs"})[0] == 409
    assert api.call("POST", "utilisateurs", {"email": "x@acme.com", "role": "Etudiants"})[0] == 400
    grp = aws["cog"].admin_list_groups_for_user(UserPoolId=aws["pool"], Username="rh@acme.com")["Groups"]
    assert grp[0]["GroupName"] == "Recruteurs"


# ------------------------------------------------------------------ candidatures
def test_postuler_regles(api):
    ajouter_etudiant(api)
    oid = creer_offre(api)
    assert api.call("POST", "candidatures", {"offreId": oid}, role="admin")[0] == 403
    s, b = api.call("POST", "candidatures", {"offreId": oid, "message": "Motivé"}, role="etudiant")
    assert s == 201
    assert api.call("POST", "candidatures", {"offreId": oid}, role="etudiant")[0] == 409  # doublon
    assert api.call("POST", "candidatures", {"offreId": "nope"}, role="etudiant")[0] == 404

    ferme = creer_offre(api, statut="Ouverte")
    api.call("PATCH", f"offres/{ferme}", {"statut": "Clôturée"})
    assert api.call("POST", "candidatures", {"offreId": ferme}, role="etudiant")[0] == 409
    perimee = creer_offre(api, date_limite="2000-01-01")
    assert api.call("POST", "candidatures", {"offreId": perimee}, role="etudiant")[0] == 409

    offres = api.call("GET", "offres", role="etudiant")[1]
    assert next(o for o in offres if o["ID"] == oid)["DejaPostule"] is True


def test_documents_upload_et_acces(api, aws):
    ajouter_etudiant(api)
    oid = creer_offre(api)
    s, up = api.call("POST", "candidatures/upload-url",
                     {"type": "cv", "filename": "Mon CV.pdf", "contentType": "application/pdf"}, role="etudiant")
    assert s == 200 and up["key"].startswith("documents/") and "policy" in up["fields"]
    for mauvais in ({"type": "cv", "contentType": "text/html"}, {"type": "photo", "contentType": "application/pdf"}):
        assert api.call("POST", "candidatures/upload-url", mauvais, role="etudiant")[0] == 400
    assert api.call("POST", "candidatures/upload-url",
                    {"type": "cv", "contentType": "application/pdf"}, role="admin")[0] == 403

    aws["s3"].put_object(Bucket="docs", Key=up["key"], Body=b"%PDF")
    s, _ = api.call("POST", "candidatures", {"offreId": oid, "cvKey": up["key"]}, role="etudiant")
    assert s == 201
    # on ne peut pas attacher le fichier d'un autre étudiant
    assert api.call("POST", "candidatures", {"offreId": creer_offre(api), "cvKey": "documents/autre/x.pdf"},
                    role="etudiant")[0] == 400

    cand = api.call("GET", "candidatures", role="etudiant")[1][0]
    assert cand["HasCv"] is True and "CvKey" not in cand
    s, docs = api.call("GET", f"candidatures/{cand['ID']}/documents", role="admin")
    assert s == 200 and docs["cv"] and docs["lettre"] is None
    assert api.call("GET", f"candidatures/{cand['ID']}/documents", role="etudiant")[0] == 200
    assert api.call("GET", f"candidatures/{cand['ID']}/documents", role="etudiant", email="autre@ecole.com")[0] == 403
    assert api.call("GET", f"candidatures/{cand['ID']}/documents", role="recruteur")[0] == 403  # pas son offre


def test_pipeline_email_notes_et_confidentialite(api):
    ajouter_etudiant(api)
    oid = creer_offre(api)
    cid = api.call("POST", "candidatures", {"offreId": oid}, role="etudiant")[1]["id"]

    assert api.call("PATCH", f"candidatures/{cid}", {"statut": "Nope"})[0] == 400
    assert api.call("PATCH", f"candidatures/{cid}", {})[0] == 400
    assert api.call("PATCH", f"candidatures/{cid}", {"statut": "Acceptée"}, role="etudiant")[0] == 403

    avant = len(sent_emails())
    assert api.call("PATCH", f"candidatures/{cid}", {"statut": "Entretien", "notes": "Très bon profil"})[0] == 200
    mails = sent_emails()
    assert len(mails) == avant + 1 and mails[-1].destinations["ToAddresses"] == ["jean.dupont@ecole.com"]
    assert "Entretien" in mails[-1].subject

    # même statut : pas de nouvel email
    api.call("PATCH", f"candidatures/{cid}", {"statut": "Entretien"})
    assert len(sent_emails()) == avant + 1

    assert api.call("PATCH", f"candidatures/{cid}", {"statut": "Acceptée"})[0] == 200
    staff = api.call("GET", "candidatures")[1][0]
    assert staff["Statut"] == "Acceptée" and staff["DateDecision"] and staff["NotesInternes"] == "Très bon profil"
    assert staff["OffreTitre"] == "Développeur Cloud" and staff["OffreEntreprise"] == "Acme"
    etu = api.call("GET", "candidatures", role="etudiant")[1][0]
    assert "NotesInternes" not in etu

    api.call("PATCH", f"candidatures/{cid}", {"statut": "Reçue"})
    assert "DateDecision" not in api.call("GET", "candidatures")[1][0]


def test_recruteur_ne_gere_que_ses_candidatures(api):
    ajouter_etudiant(api)
    oid_admin = creer_offre(api)
    oid_rh = creer_offre(api, role="recruteur")
    c1 = api.call("POST", "candidatures", {"offreId": oid_admin}, role="etudiant")[1]["id"]
    c2 = api.call("POST", "candidatures", {"offreId": oid_rh}, role="etudiant")[1]["id"]
    vues = [c["ID"] for c in api.call("GET", "candidatures", role="recruteur")[1]]
    assert vues == [c2]
    assert api.call("PATCH", f"candidatures/{c1}", {"statut": "Refusée"}, role="recruteur")[0] == 403
    assert api.call("PATCH", f"candidatures/{c2}", {"statut": "Refusée"}, role="recruteur")[0] == 200


def test_isolation_entre_etudiants(api):
    ajouter_etudiant(api)
    oid = creer_offre(api)
    api.call("POST", "candidatures", {"offreId": oid}, role="etudiant")
    assert len(api.call("GET", "candidatures", role="etudiant")[1]) == 1
    assert api.call("GET", "candidatures", role="etudiant", email="autre@ecole.com")[1] == []


# ------------------------------------------------------------------ RGPD
def test_suppression_rgpd_complete(api, aws):
    ajouter_etudiant(api)
    oid = creer_offre(api)
    key = api.call("POST", "candidatures/upload-url",
                   {"type": "cv", "contentType": "application/pdf"}, role="etudiant")[1]["key"]
    aws["s3"].put_object(Bucket="docs", Key=key, Body=b"x")
    api.call("POST", "candidatures", {"offreId": oid, "cvKey": key}, role="etudiant")

    s, b = api.call("DELETE", "etudiants/jean.dupont@ecole.com")
    assert s == 200 and b["candidatures_supprimees"] == 1
    assert api.call("GET", "etudiants")[1] == []
    assert api.call("GET", "candidatures")[1] == []
    assert aws["s3"].list_objects_v2(Bucket="docs").get("KeyCount", 0) == 0
    assert aws["cog"].list_users(UserPoolId=aws["pool"])["Users"] == []


# ------------------------------------------------------------------ stats / audit
def test_stats_notifications_audit(api):
    ajouter_etudiant(api)
    o1, o2 = creer_offre(api), creer_offre(api, domaine="Cyber")
    c1 = api.call("POST", "candidatures", {"offreId": o1}, role="etudiant")[1]["id"]
    api.call("PATCH", f"candidatures/{c1}", {"statut": "Acceptée"})

    st = api.call("GET", "stats")[1]
    assert st["total_offres"] == 2 and st["offres_ouvertes"] == 2 and st["total_etudiants"] == 1
    assert st["candidatures_par_statut"] == {"Acceptée": 1}
    assert st["candidatures_par_domaine"] == {"Cloud": 1}
    assert st["taux_acceptation"] == 100 and st["delai_moyen_jours"] is not None
    assert st["nb_offres_sans_candidature"] == 1 and st["offres_sans_candidature"][0]["ID"] == o2

    actions = {a["Action"] for a in api.call("GET", "audit")[1]}
    assert {"offre.creer", "etudiant.ajouter", "candidature.statut"} <= actions
    assert len(api.call("GET", "audit", query={"limit": "1"})[1]) == 1
    types = {n["Type"] for n in api.call("GET", "notifications")[1]}
    assert {"nouvelle_offre", "statut"} <= types


# ------------------------------------------------------------------ notifier S3
def test_notifier_upload_s3(notifier, aws):
    aws["s3"].put_object(Bucket="offres", Key="Cloud_Architecte AWS.pdf", Body=b"x")
    aws["ddb"].Table("Etudiants").put_item(Item={"Email": "a@x.co", "Nom": "A", "Domaines": ["Cloud", "General"]})
    event = {"Records": [{"s3": {"bucket": {"name": "offres"}, "object": {"key": "Cloud_Architecte+AWS.pdf"}}}]}
    res = notifier.lambda_handler(event, None)["resultats"][0]
    assert res["domaine"] == "Cloud" and res["notified"] and res["destinataires"] == 1

    offre = aws["ddb"].Table("Offres").scan()["Items"][0]
    assert offre["Titre"] == "Architecte AWS" and offre["FichierKey"] == "Cloud_Architecte AWS.pdf"
    assert offre["Statut"] == "Ouverte" and offre["URL"] == ""
    assert aws["ddb"].Table("Notifications").scan()["Count"] == 1


def test_notifier_domaine_general(notifier):
    assert notifier.domaine_depuis_cle("Offre_Generale.txt") == "General"
    assert notifier.domaine_depuis_cle("sans_prefixe_connu.pdf") == "General"
    assert notifier.domaine_depuis_cle("dossier/Web_Dev.pdf") == "Web"


# ------------------------------------------------------------------ scheduler
def _offre(aws, oid, **kw):
    item = {"ID": oid, "Titre": f"Offre {oid}", "Domaine": "Cloud", "Statut": "Ouverte",
            "CreeLe": datetime.now(timezone.utc).isoformat(timespec="seconds"), "DateLimite": ""}
    item.update(kw)
    aws["ddb"].Table("Offres").put_item(Item=item)


def _etudiant(aws, email, domaines=("Cloud", "General")):
    aws["ddb"].Table("Etudiants").put_item(Item={"Email": email, "Nom": email.split("@")[0], "Domaines": list(domaines)})


def test_digest(scheduler, aws):
    _etudiant(aws, "a@ecole.com")
    _etudiant(aws, "b@ecole.com", ("Cyber", "General"))
    assert scheduler.lambda_handler({"task": "digest"}, None)["envoyes"] == 0  # aucune offre
    _offre(aws, "1")
    _offre(aws, "vieille", CreeLe=(datetime.now(timezone.utc) - timedelta(days=30)).isoformat())
    _offre(aws, "fermee", Statut="Clôturée")
    res = scheduler.lambda_handler({"task": "digest"}, None)
    assert res == {"envoyes": 1, "offres": 1}  # seul a@ (Cloud) est concerné
    assert sent_emails()[-1].destinations["ToAddresses"] == ["a@ecole.com"]


def test_rappels_et_cloture_auto(scheduler, aws):
    _etudiant(aws, "a@ecole.com")
    _etudiant(aws, "b@ecole.com")
    dans_2j = (datetime.now(timezone.utc) + timedelta(days=2)).strftime("%Y-%m-%d")
    passee = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
    _offre(aws, "proche", DateLimite=dans_2j)
    _offre(aws, "expiree", DateLimite=passee)
    _offre(aws, "loin", DateLimite="2099-01-01")
    aws["ddb"].Table("Candidatures").put_item(
        Item={"ID": "c1", "OffreID": "proche", "EtudiantEmail": "b@ecole.com", "Statut": "Reçue"})

    res = scheduler.lambda_handler({"task": "rappels"}, None)
    assert res == {"offres_cloturees": 1, "offres_rappelees": 1, "emails": 1}  # b a déjà postulé
    assert sent_emails()[-1].destinations["ToAddresses"] == ["a@ecole.com"]
    statuts = {o["ID"]: o["Statut"] for o in aws["ddb"].Table("Offres").scan()["Items"]}
    assert statuts == {"proche": "Ouverte", "expiree": "Clôturée", "loin": "Ouverte"}
    # idempotent : pas de second rappel
    assert scheduler.lambda_handler({"task": "rappels"}, None) == {"offres_cloturees": 0, "offres_rappelees": 0, "emails": 0}


def test_scheduler_tache_inconnue(scheduler):
    import pytest
    with pytest.raises(ValueError):
        scheduler.lambda_handler({"task": "nope"}, None)
