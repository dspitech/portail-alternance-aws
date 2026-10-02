"""Fixtures : un faux AWS (moto) + chargement des Lambdas comme en production."""

import importlib
import json
import os
import sys

import boto3
import pytest
from moto import mock_aws

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGION = "eu-west-3"
SENDER = "recrutement@ecole.com"
MODULES = ["common", "h_offres", "h_etudiants", "h_candidatures", "h_misc", "lambda_function"]


def _load(dirname):
    for m in MODULES:
        sys.modules.pop(m, None)
    for d in ("lambda_api", "lambda_notifier", "lambda_scheduler"):
        p = os.path.join(BACKEND, d)
        if p in sys.path:
            sys.path.remove(p)
    sys.path.insert(0, os.path.join(BACKEND, dirname))
    return importlib.import_module("lambda_function")


@pytest.fixture
def aws(monkeypatch):
    with mock_aws():
        for k, v in {"AWS_DEFAULT_REGION": REGION, "AWS_REGION": REGION,
                     "AWS_ACCESS_KEY_ID": "x", "AWS_SECRET_ACCESS_KEY": "x"}.items():
            monkeypatch.setenv(k, v)

        ddb = boto3.client("dynamodb")

        def table(name, key, extra_attrs=(), gsis=()):
            attrs = [{"AttributeName": key, "AttributeType": "S"}] + [
                {"AttributeName": a, "AttributeType": "S"} for a in extra_attrs]
            kwargs = dict(TableName=name, AttributeDefinitions=attrs, BillingMode="PAY_PER_REQUEST",
                          KeySchema=[{"AttributeName": key, "KeyType": "HASH"}])
            if gsis:
                kwargs["GlobalSecondaryIndexes"] = [
                    {"IndexName": f"{a}-index", "KeySchema": [{"AttributeName": a, "KeyType": "HASH"}],
                     "Projection": {"ProjectionType": "ALL"}} for a in gsis]
            ddb.create_table(**kwargs)

        table("Offres", "ID")
        table("Etudiants", "Email")
        table("Candidatures", "ID", ("OffreID", "EtudiantEmail"), ("OffreID", "EtudiantEmail"))
        table("Notifications", "ID")
        table("Audit", "ID")

        sns = boto3.client("sns")
        topics = {d: sns.create_topic(Name=f"alertes-{d}")["TopicArn"]
                  for d in ("Cloud", "Cyber", "General")}

        s3 = boto3.client("s3")
        s3.create_bucket(Bucket="docs", CreateBucketConfiguration={"LocationConstraint": REGION})
        s3.create_bucket(Bucket="offres", CreateBucketConfiguration={"LocationConstraint": REGION})

        boto3.client("ses").verify_email_identity(EmailAddress=SENDER)

        cog = boto3.client("cognito-idp")
        pool = cog.create_user_pool(PoolName="p")["UserPool"]["Id"]
        for g in ("Admins", "Recruteurs", "Etudiants"):
            cog.create_group(GroupName=g, UserPoolId=pool)

        for k, v in {
            "TABLE_OFFRES": "Offres", "TABLE_ETUDIANTS": "Etudiants", "TABLE_CANDIDATURES": "Candidatures",
            "TABLE_NOTIFICATIONS": "Notifications", "TABLE_AUDIT": "Audit",
            "SNS_TOPIC_ARNS": json.dumps(topics), "COGNITO_USER_POOL_ID": pool,
            "DOCS_BUCKET": "docs", "OFFRES_BUCKET": "offres", "SENDER_EMAIL": SENDER,
            "DASHBOARD_URL": "https://dash.example.com", "SES_SANDBOX_MODE": "true",
            "CORS_ALLOWED_ORIGIN": "https://dash.example.com", "RAPPEL_JOURS": "3",
        }.items():
            monkeypatch.setenv(k, v)

        yield {"topics": topics, "pool": pool, "s3": s3, "cog": cog, "ddb": boto3.resource("dynamodb")}


class Api:
    def __init__(self, module):
        self.m = module

    def call(self, method, path, body=None, role="admin", email=None, query=None):
        email = email or {"admin": "admin@ecole.com", "recruteur": "rh@acme.com",
                          "etudiant": "jean.dupont@ecole.com"}.get(role, "x@x.com")
        groupe = {"admin": "Admins", "recruteur": "Recruteurs", "etudiant": "Etudiants", "aucun": ""}[role]
        event = {"httpMethod": method, "pathParameters": {"proxy": path},
                 "body": json.dumps(body) if body is not None else None,
                 "queryStringParameters": query,
                 "requestContext": {"authorizer": {"claims": {"email": email, "cognito:groups": groupe}}}}
        r = self.m.lambda_handler(event, None)
        return r["statusCode"], json.loads(r["body"])


@pytest.fixture
def api(aws):
    return Api(_load("lambda_api"))


@pytest.fixture
def scheduler(aws):
    return _load("lambda_scheduler")


@pytest.fixture
def notifier(aws):
    return _load("lambda_notifier")


def sent_emails():
    from moto.core import DEFAULT_ACCOUNT_ID
    from moto.ses import ses_backends
    return ses_backends[DEFAULT_ACCOUNT_ID][REGION].sent_messages
