/**
 * Authentification via l'UI hébergée Cognito (Authorization Code + PKCE).
 * Pas de librairie externe : juste fetch + crypto.subtle.
 * Les tokens vivent en sessionStorage (effacés à la fermeture de l'onglet).
 */
const Auth = (() => {
  const SESSION_KEY = "alternance_tokens";

  function base64url(buffer) {
    return btoa(String.fromCharCode(...new Uint8Array(buffer)))
      .replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  }

  async function makePkcePair() {
    const verifierBytes = crypto.getRandomValues(new Uint8Array(32));
    const verifier = base64url(verifierBytes);
    const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier));
    const challenge = base64url(digest);
    return { verifier, challenge };
  }

  async function redirectToLogin() {
    const { verifier, challenge } = await makePkcePair();
    sessionStorage.setItem("pkce_verifier", verifier);

    const url = new URL(`https://${CONFIG.COGNITO_DOMAIN}/oauth2/authorize`);
    url.searchParams.set("client_id", CONFIG.COGNITO_CLIENT_ID);
    url.searchParams.set("response_type", "code");
    url.searchParams.set("scope", "openid email profile");
    url.searchParams.set("redirect_uri", CONFIG.COGNITO_REDIRECT_URI);
    url.searchParams.set("code_challenge_method", "S256");
    url.searchParams.set("code_challenge", challenge);
    window.location.href = url.toString();
  }

  async function exchangeCodeForTokens(code) {
    const verifier = sessionStorage.getItem("pkce_verifier");
    const resp = await fetch(`https://${CONFIG.COGNITO_DOMAIN}/oauth2/token`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({
        grant_type: "authorization_code",
        client_id: CONFIG.COGNITO_CLIENT_ID,
        code,
        redirect_uri: CONFIG.COGNITO_REDIRECT_URI,
        code_verifier: verifier,
      }),
    });
    if (!resp.ok) throw new Error("Échange du code impossible");
    const tokens = await resp.json();
    sessionStorage.setItem(SESSION_KEY, JSON.stringify(tokens));
    sessionStorage.removeItem("pkce_verifier");
    return tokens;
  }

  function getIdToken() {
    const raw = sessionStorage.getItem(SESSION_KEY);
    if (!raw) return null;
    return JSON.parse(raw).id_token || null;
  }

  function decodeIdToken() {
    const token = getIdToken();
    if (!token) return null;
    const payload = token.split(".")[1];
    return JSON.parse(atob(payload.replace(/-/g, "+").replace(/_/g, "/")));
  }

  function logout() {
    sessionStorage.removeItem(SESSION_KEY);
    const url = new URL(`https://${CONFIG.COGNITO_DOMAIN}/logout`);
    url.searchParams.set("client_id", CONFIG.COGNITO_CLIENT_ID);
    url.searchParams.set("logout_uri", CONFIG.COGNITO_LOGOUT_URI);
    window.location.href = url.toString();
  }

  /** À appeler au chargement de index.html. Redirige vers login si nécessaire. */
  async function ensureAuthenticated() {
    const params = new URLSearchParams(window.location.search);
    const code = params.get("code");

    if (code) {
      await exchangeCodeForTokens(code);
      window.history.replaceState({}, document.title, window.location.pathname);
    }

    if (!getIdToken()) {
      window.location.href = "login.html";
      return null;
    }
    return decodeIdToken();
  }

  return { redirectToLogin, ensureAuthenticated, getIdToken, decodeIdToken, logout };
})();
