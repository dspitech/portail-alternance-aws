const Api = (() => {
  async function call(path, { method = "GET", body } = {}) {
    const token = Auth.getIdToken();
    const resp = await fetch(`${CONFIG.API_BASE_URL}/${path}`, {
      method,
      headers: { "Content-Type": "application/json", ...(token ? { Authorization: token } : {}) },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });

    // Token expiré (validité 1 h) : on repasse par le login, la session Cognito est souvent encore valide
    if (resp.status === 401) {
      sessionStorage.removeItem("alternance_tokens");
      window.location.href = "login.html";
      throw new Error("Session expirée");
    }
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) throw new Error(data.error || data.message || `Erreur ${resp.status}`);
    return data;
  }

  const q = encodeURIComponent;
  return {
    me: () => call("me"),
    majProfil: (profil) => call("me/profile", { method: "PUT", body: profil }),

    listOffres: () => call("offres"),
    creerOffre: (o) => call("offres", { method: "POST", body: o }),
    modifierOffre: (id, o) => call(`offres/${id}`, { method: "PATCH", body: o }),
    supprimerOffre: (id) => call(`offres/${id}`, { method: "DELETE" }),
    fichierOffre: (id) => call(`offres/${id}/fichier`),
    notifier: (offreId) => call("notify", { method: "POST", body: { offreId } }),

    listEtudiants: () => call("etudiants"),
    creerEtudiant: (e) => call("etudiants", { method: "POST", body: e }),
    importerEtudiants: (etudiants) => call("etudiants/import", { method: "POST", body: { etudiants } }),
    supprimerEtudiant: (email) => call(`etudiants/${q(email)}`, { method: "DELETE" }),
    creerCompteStaff: (email, role) => call("utilisateurs", { method: "POST", body: { email, role } }),

    listCandidatures: () => call("candidatures"),
    postuler: (payload) => call("candidatures", { method: "POST", body: payload }),
    uploadUrl: (payload) => call("candidatures/upload-url", { method: "POST", body: payload }),
    documents: (id) => call(`candidatures/${id}/documents`),
    majCandidature: (id, patch) => call(`candidatures/${id}`, { method: "PATCH", body: patch }),

    stats: () => call("stats"),
    notifications: () => call("notifications"),
    audit: () => call("audit"),
  };
})();
