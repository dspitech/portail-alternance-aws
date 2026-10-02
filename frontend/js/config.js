// Valeurs à remplacer par les outputs Terraform après `terraform apply`
// (terraform output -json vous donne tout ça d'un coup)
const CONFIG = {
  API_BASE_URL: "https://REMPLACER.execute-api.eu-west-3.amazonaws.com/dev",
  COGNITO_DOMAIN: "REMPLACER.auth.eu-west-3.amazoncognito.com",
  COGNITO_CLIENT_ID: "REMPLACER",
  COGNITO_REDIRECT_URI: window.location.origin + "/index.html",
  COGNITO_LOGOUT_URI: window.location.origin + "/login.html",
};
