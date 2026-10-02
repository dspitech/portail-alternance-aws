"""
Lambda unique derrière API Gateway (intégration proxy {proxy+}).

Routes (rôles : A = Admins, R = Recruteurs, E = Etudiants) :

  GET    /me                              tous     profil + rôle
  PUT    /me/profile                      E        modifier nom / domaines suivis

  GET    /offres                          tous     (R : ses offres ; E : + DejaPostule)
  POST   /offres                          A R      créer (+ notifier)
  PATCH  /offres/{id}                     A R*     modifier / clôturer / rouvrir
  DELETE /offres/{id}                     A R*
  GET    /offres/{id}/fichier             tous     URL fraîche du fichier de l'offre
  POST   /notify                          A R*     renvoyer l'alerte d'une offre

  GET    /etudiants                       A
  POST   /etudiants                       A
  POST   /etudiants/import                A        import en masse (max 50)
  DELETE /etudiants/{email}               A        purge RGPD complète

  GET    /candidatures                    tous     (A : toutes ; R : ses offres ; E : les siennes)
  POST   /candidatures                    E        postuler
  POST   /candidatures/upload-url         E        POST présigné pour CV / lettre
  GET    /candidatures/{id}/documents     A R* E*  URLs de lecture des documents
  PATCH  /candidatures/{id}               A R*     statut du pipeline et/ou notes internes

  POST   /utilisateurs                    A        créer un compte Admin / Recruteur
  GET    /stats                           A
  GET    /notifications                   A        historique des envois
  GET    /audit                           A        journal d'audit

  (* = uniquement sur ses propres offres / candidatures)

L'API Gateway valide le JWT Cognito ; cette Lambda lit les groupes dans les claims
pour appliquer les droits.
"""

import json

from botocore.exceptions import ClientError

from common import ApiError, current_user, response
from h_candidatures import handle_candidatures
from h_etudiants import handle_etudiants
from h_misc import (handle_audit, handle_me, handle_notifications, handle_stats,
                    handle_utilisateurs)
from h_offres import handle_notify, handle_offres


def lambda_handler(event, context):
    try:
        method = event.get("httpMethod", "GET")
        raw_path = (event.get("pathParameters") or {}).get("proxy", "") or ""
        parts = [p for p in raw_path.split("/") if p]
        resource = parts[0] if parts else ""
        rid = parts[1] if len(parts) > 1 else None
        sub = parts[2] if len(parts) > 2 else None
        try:
            body = json.loads(event["body"]) if event.get("body") else {}
        except json.JSONDecodeError:
            raise ApiError(400, "Corps de requête JSON invalide")
        if not isinstance(body, dict):
            raise ApiError(400, "Le corps de la requête doit être un objet JSON")

        user = current_user(event)
        if user["role"] == "inconnu" and resource != "me":
            raise ApiError(403, "Aucun rôle attribué à ce compte")

        routes = {
            "me": handle_me,
            "offres": handle_offres,
            "etudiants": handle_etudiants,
            "candidatures": handle_candidatures,
            "utilisateurs": handle_utilisateurs,
            "stats": handle_stats,
            "notifications": handle_notifications,
            "audit": handle_audit,
        }
        if resource == "notify":
            return handle_notify(method, body, user)
        handler = routes.get(resource)
        if not handler:
            return response(404, {"error": f"Route inconnue : /{raw_path}"})
        return handler(method, rid, sub, body, user, event)

    except ApiError as e:
        return response(e.status_code, {"error": e.message})
    except ClientError as e:
        print(f"Erreur AWS : {e}")
        return response(500, {"error": "Erreur AWS interne"})
    except Exception as e:  # garde-fou : jamais de stack trace côté client
        print(f"Erreur inattendue : {type(e).__name__}: {e}")
        return response(500, {"error": "Erreur interne"})
