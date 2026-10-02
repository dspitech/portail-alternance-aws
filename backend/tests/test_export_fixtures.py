"""Exporte les VRAIES réponses de l'API vers frontend/tests/fixtures.json (test de contrat
avec le frontend). Ne s'exécute que si EXPORT_FIXTURES=1.
    EXPORT_FIXTURES=1 pytest backend/tests/test_export_fixtures.py"""

import json
import os

import pytest

pytestmark = pytest.mark.skipif(os.environ.get("EXPORT_FIXTURES") != "1", reason="export à la demande")

OUT = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "tests", "fixtures.json")


def test_export(api, aws):
    ok = lambda r: (r[0] < 300) or pytest.fail(r)  # noqa: E731
    ok(api.call("POST", "etudiants", {"email": "jean.dupont@ecole.com", "domaines": ["Cloud"]}))
    o1 = api.call("POST", "offres", {"titre": "Dev Cloud", "domaine": "Cloud", "entreprise": "Acme", "lieu": "Paris",
                                     "rythme": "3j/2j", "duree": "12 mois", "date_limite": "2099-12-31"})[1]["id"]
    ok(api.call("POST", "offres", {"titre": "Analyste SOC", "domaine": "Cyber", "notifier": False}, role="recruteur"))
    aws["s3"].put_object(Bucket="docs", Key="documents/x/cv.pdf", Body=b"x")
    key = api.call("POST", "candidatures/upload-url", {"type": "cv", "contentType": "application/pdf"}, role="etudiant")[1]["key"]
    aws["s3"].put_object(Bucket="docs", Key=key, Body=b"x")
    cid = api.call("POST", "candidatures", {"offreId": o1, "cvKey": key, "message": "Motivé"}, role="etudiant")[1]["id"]
    ok(api.call("PATCH", f"candidatures/{cid}", {"statut": "Entretien", "notes": "Bon profil"}))

    routes_staff = ["me", "offres", "candidatures"]
    data = {"cid": cid, "oid": o1}
    for role in ("admin", "recruteur", "etudiant"):
        routes = routes_staff + (["etudiants", "stats", "notifications", "audit"] if role == "admin" else [])
        data[role] = {r: api.call("GET", r, role=role)[1] for r in routes}
    data["admin"][f"candidatures/{cid}/documents"] = api.call("GET", f"candidatures/{cid}/documents")[1]
    with open(OUT, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=1, default=str)
