# Prérequis : Terraform + AWS CLI sur Ubuntu Server

Installation et configuration des outils nécessaires au déploiement de **projet-alternance-enterprise** sur AWS (S3, Lambda, DynamoDB, Cognito, API Gateway, CloudFront, SNS, SES, EventBridge).

| Élément | Valeur |
|---|---|
| Système cible | Ubuntu Server 20.04 / 22.04 / 24.04 (x86_64 ou ARM64) |
| Terraform | ≥ 1.5.0 |
| Provider | `hashicorp/aws ~> 5.0` |
| Runtime Lambda | `python3.12` |
| Région par défaut | `eu-west-3` (Paris) |
| Outils requis par `scripts/deploy.sh` | `terraform`, `aws cli` configuré, `jq` |

## Sommaire

1. [Préparation du système](#1-préparation-du-système)
2. [Installation de Terraform](#2-installation-de-terraform)
3. [Installation d'AWS CLI v2](#3-installation-daws-cli-v2)
4. [Créer les identifiants AWS](#4-créer-les-identifiants-aws)
5. [Configurer AWS CLI](#5-configurer-aws-cli)
6. [Outils pour les tests locaux (optionnel)](#6-outils-pour-les-tests-locaux-optionnel)
7. [Récupérer et préparer le projet](#7-récupérer-et-préparer-le-projet)
8. [Vérifier puis déployer](#8-vérifier-puis-déployer)
9. [Après le premier déploiement](#9-après-le-premier-déploiement)
10. [Nettoyage](#10-nettoyage)
11. [Bonnes pratiques](#11-bonnes-pratiques)
12. [Dépannage](#12-dépannage)

---

## 1. Préparation du système

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y curl wget unzip gnupg software-properties-common \
                    ca-certificates lsb-release git jq
```

## 2. Installation de Terraform

Dépôt officiel HashiCorp.

```bash
# Clé GPG
wget -O- https://apt.releases.hashicorp.com/gpg | \
  sudo gpg --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg

# Dépôt
echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] \
https://apt.releases.hashicorp.com $(lsb_release -cs) main" | \
  sudo tee /etc/apt/sources.list.d/hashicorp.list

# Installation
sudo apt update
sudo apt install -y terraform

# Vérification (version >= 1.5.0)
terraform -version
```

Autocomplétion (optionnel) :

```bash
terraform -install-autocomplete
source ~/.bashrc
```

## 3. Installation d'AWS CLI v2

Vérifier l'architecture avec `uname -m`, puis télécharger l'archive correspondante.

```bash
# x86_64
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"

# aarch64 (ARM), à utiliser à la place de la ligne ci-dessus
# curl "https://awscli.amazonaws.com/awscli-exe-linux-aarch64.zip" -o "awscliv2.zip"

unzip awscliv2.zip
sudo ./aws/install
aws --version

# Nettoyage
rm -rf awscliv2.zip aws/
```

Mise à jour ultérieure : re-télécharger l'archive puis `sudo ./aws/install --update`.

## 4. Créer les identifiants AWS

> N'utilisez pas le compte root. Créez un utilisateur IAM dédié.

1. Console AWS → **IAM → Users → Create user** (ex. `terraform-user`).
2. Permissions : **AdministratorAccess**. C'est le plus simple pour ce projet, car Terraform crée des rôles IAM, des Lambdas, Cognito, CloudFront, etc.
3. Onglet **Security credentials → Create access key**, cas d'usage *Command Line Interface (CLI)*.
4. Noter l'**Access Key ID** et la **Secret Access Key**.

> ⚠️ La clé secrète n'est affichée qu'une seule fois.

## 5. Configurer AWS CLI

```bash
aws configure
```

```text
AWS Access Key ID [None]:     AKIAXXXXXXXXXXXXXXXX
AWS Secret Access Key [None]: ****************************************
Default region name [None]:   eu-west-3
Default output format [None]: json
```

```bash
chmod 600 ~/.aws/credentials

# Test : affiche l'Account ID et l'ARN de l'utilisateur
aws sts get-caller-identity
```

> ⚠️ La région du CLI doit être identique à `region` dans `terraform.tfvars` (`eu-west-3`). Sinon `deploy.sh` (`aws s3 sync`, `create-invalidation`) peut viser la mauvaise région.

**Plusieurs profils (variante)** :

```bash
aws configure --profile alternance
export AWS_PROFILE=alternance
```

## 6. Outils pour les tests locaux (optionnel)

`scripts/test.sh` lance pytest (backend), jsdom (frontend) et `terraform validate`. Il faut Python 3, pip et Node.js.

```bash
sudo apt install -y python3 python3-pip python3-venv nodejs npm

# Environnement virtuel recommandé (Ubuntu 24.04 bloque pip hors venv)
cd ~/projet-alternance-enterprise
python3 -m venv .venv
source .venv/bin/activate
./scripts/test.sh
```

## 7. Récupérer et préparer le projet

Après transfert de l'archive sur la VM (`scp`, WinSCP, etc.) :

```bash
cd ~
unzip projet-alternance-enterprise.zip
cd projet-alternance-enterprise/terraform

cp terraform.tfvars.example terraform.tfvars
nano terraform.tfvars
```

**À modifier obligatoirement** :

```hcl
admin_email = "votre.email@exemple.com"
```

> ⚠️ Le fichier d'exemple contient l'adresse d'une autre personne. Mettez la vôtre : c'est là que arrivent le mot de passe temporaire Cognito et les confirmations SES / SNS.

Valeurs par défaut :

```hcl
project_name = "alternance-alerts"
environment  = "dev"
region       = "eu-west-3"
```

## 8. Vérifier puis déployer

> Le README du projet précise que Terraform n'a **jamais été exécuté** sur ce code. Validez toujours avant de déployer.

```bash
cd ~/projet-alternance-enterprise/terraform
terraform init
terraform fmt -recursive
terraform validate
terraform plan
```

Déploiement complet (apply, génération de `frontend/js/config.js`, upload S3, invalidation CloudFront) :

```bash
cd ~/projet-alternance-enterprise
chmod +x scripts/*.sh
./scripts/deploy.sh
```

> ⚠️ `deploy.sh` exécute `terraform apply -auto-approve` sans demander de confirmation.

Récupérer les URLs et noms de ressources :

```bash
cd terraform
terraform output
terraform output -raw dashboard_url
```

## 9. Après le premier déploiement

1. **SES** : cliquer sur le lien de vérification reçu à l'adresse expéditrice (`sender_email`, par défaut `admin_email`). Sans cela, aucun email de statut, résumé ou rappel ne part.
2. **Admin** : l'email Cognito contient le mot de passe temporaire. Ouvrir l'URL `dashboard_url`.
3. **SNS** : confirmer l'abonnement de chaque topic (un email par domaine).
4. **Test d'une offre par fichier** :
   ```bash
   aws s3 cp Cloud_Architecte_AWS.pdf s3://<offres_bucket_name>/
   ```

## 10. Nettoyage

Pour éviter les frais, vider d'abord les buckets S3 contenant des objets, puis détruire l'infrastructure.

```bash
cd ~/projet-alternance-enterprise/terraform
terraform output                         # repérer les noms de buckets
aws s3 rm s3://NOM_BUCKET --recursive    # pour chaque bucket (offres, documents, frontend)
terraform destroy
```

## 11. Bonnes pratiques

- Ne jamais commiter `~/.aws/credentials`, `terraform.tfvars` ni `*.tfstate`.
- Activer le **MFA** sur le compte AWS et créer un **budget d'alerte** (Billing → Budgets).
- Travail en équipe : activer le backend **S3 + DynamoDB lock** (bloc commenté dans `terraform/providers.tf`).
- Si la VM Ubuntu est une EC2 : préférer un **rôle IAM** attaché à l'instance plutôt que des clés d'accès.
- Alternative aux clés dans `~/.aws` :
  ```bash
  export AWS_ACCESS_KEY_ID="..."
  export AWS_SECRET_ACCESS_KEY="..."
  export AWS_DEFAULT_REGION="eu-west-3"
  ```

## 12. Dépannage

| Symptôme | Solution |
|---|---|
| `aws: command not found` | `source ~/.bashrc` ; vérifier `/usr/local/bin/aws` |
| `Unable to locate credentials` | Relancer `aws configure` ; vérifier `AWS_PROFILE` |
| `InvalidClientTokenId` | Clé mal copiée ; recréer la clé d'accès |
| `UnauthorizedOperation` / `AccessDenied` | Permissions IAM insuffisantes |
| `jq: command not found` | `sudo apt install -y jq` |
| `externally-managed-environment` (pip) | Utiliser un venv (voir [section 6](#6-outils-pour-les-tests-locaux-optionnel)) |
| `Failed to query available provider packages` | Vérifier Internet / DNS / proxy de la VM |
| Email SES non reçu | Lien de vérification non cliqué (compte SES en sandbox) |
| Cognito limité à ~50 emails/jour | Comportement normal de l'email par défaut |

**Désinstallation** :

```bash
sudo apt remove terraform
sudo rm /usr/local/bin/aws /usr/local/bin/aws_completer
sudo rm -rf /usr/local/aws-cli
```
