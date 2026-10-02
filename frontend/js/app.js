/* Dashboard : vues, formulaires et actions. Dépend de config.js, auth.js, api.js, ui.js. */

const STATUTS = ["Reçue", "Présélectionnée", "Entretien", "Acceptée", "Refusée"];
const TYPES_NOTIF = {
  nouvelle_offre: "Nouvelle offre", rappel_manuel: "Rappel manuel", digest: "Résumé hebdo",
  rappel_deadline: "Rappel date limite", statut: "Changement de statut",
};
const TYPES_FICHIER = { pdf: "application/pdf", doc: "application/msword",
  docx: "application/vnd.openxmlformats-officedocument.wordprocessingml.document" };
const TAILLE_MAX = 5 * 1024 * 1024;
const VUES_AUTORISEES = {
  offres: ["admin", "recruteur", "etudiant"], candidatures: ["admin", "recruteur", "etudiant"],
  etudiants: ["admin"], notifications: ["admin"], stats: ["admin"], audit: ["admin"], profil: ["etudiant"],
};

const ME = { role: null, email: "", profil: null };
let DOMAINES = [];
const CACHE = { offres: [], cands: [], etudiants: [] };
const TABLES = {};

const isStaff = () => ME.role === "admin" || ME.role === "recruteur";
const badge = (txt, cls = "") => `<span class="badge ${cls}">${escapeHtml(txt)}</span>`;
const btn = (label, action, id, cls = "btn-secondary") =>
  `<button class="${cls}" data-action="${action}" data-id="${escapeHtml(id)}">${escapeHtml(label)}</button>`;
const aujourdhui = () => new Date().toISOString().slice(0, 10);
const offreExpiree = (o) => (o.Statut || "Ouverte") === "Ouverte" && o.DateLimite && o.DateLimite < aujourdhui();
const titreOffre = (o) => o.Titre || o.NomFichier || "(sans titre)";

function badgeStatutOffre(o) {
  if (offreExpiree(o)) return badge("Échéance passée", "closed");
  return badge(o.Statut || "Ouverte", (o.Statut || "Ouverte") === "Clôturée" ? "closed" : "");
}
function badgeStatutCand(s) {
  const cls = { "Reçue": "pending", "Présélectionnée": "info", "Entretien": "info", "Refusée": "rejected" }[s] || "";
  return badge(s, cls);
}

// ---------------------------------------------------------------------
// Navigation
// ---------------------------------------------------------------------

function applyRoles() {
  document.querySelectorAll("[data-roles]").forEach((el) => {
    el.style.display = el.dataset.roles.split(",").includes(ME.role) ? "" : "none";
  });
}

function showView(name) {
  if (!VUES_AUTORISEES[name]?.includes(ME.role)) return;
  document.querySelectorAll(".nav-item").forEach((b) => b.classList.toggle("active", b.dataset.view === name));
  document.querySelectorAll(".view").forEach((s) => s.classList.toggle("hidden", s.id !== `view-${name}`));
  ({ offres: renderOffres, candidatures: renderCandidatures, etudiants: renderEtudiants,
     notifications: renderNotifications, stats: renderStats, audit: renderAudit, profil: renderProfil })[name]();
}

async function safe(fn) {
  try { return await fn(); } catch (e) { toast(e.message, "error"); }
}

// ---------------------------------------------------------------------
// OFFRES
// ---------------------------------------------------------------------

function actionsOffre(o) {
  const b = [btn("Détails", "offre-detail", o.ID)];
  if (ME.role === "etudiant") {
    if (o.DejaPostule) b.push(badge("Postulé", "info"));
    else if ((o.Statut || "Ouverte") === "Ouverte" && !offreExpiree(o)) b.push(btn("Postuler", "offre-postuler", o.ID));
  } else if (isStaff()) {
    b.push(btn("Modifier", "offre-modifier", o.ID));
    b.push(btn((o.Statut || "Ouverte") === "Clôturée" ? "Rouvrir" : "Clôturer", "offre-basculer", o.ID));
  }
  return `<div class="row-actions">${b.join("")}</div>`;
}

function initTableOffres() {
  const cols = [
    { key: "titre", label: "Offre", sort: (o) => titreOffre(o).toLowerCase(),
      html: (o) => `<div class="cell-title">${escapeHtml(titreOffre(o))}</div>
        <div class="cell-sub">${escapeHtml([o.Entreprise, o.Lieu].filter(Boolean).join(" · "))}</div>` },
    { key: "domaine", label: "Domaine", sort: (o) => o.Domaine, html: (o) => badge(o.Domaine) },
    { key: "rythme", label: "Rythme / durée", html: (o) => escapeHtml([o.Rythme, o.Duree].filter(Boolean).join(" · ") || "—") },
    { key: "limite", label: "Date limite", sort: (o) => o.DateLimite || "9999", html: (o) => fmtDate(o.DateLimite) },
    { key: "statut", label: "Statut", sort: (o) => o.Statut || "Ouverte", html: badgeStatutOffre },
    { key: "date", label: "Publiée", sort: (o) => o.CreeLe || "", html: (o) => fmtDate(o.CreeLe) },
    { key: "actions", label: "", html: actionsOffre },
  ];
  if (isStaff()) cols.splice(5, 0, { key: "nb", label: "Candidatures", sort: (o) => o.NbCandidatures || 0, html: (o) => o.NbCandidatures || 0 });
  TABLES.offres = new DataTable("offres-table", {
    columns: cols, defaultSort: { key: "date", dir: "desc" }, empty: "Aucune offre.",
    searchText: (o) => [titreOffre(o), o.Entreprise, o.Lieu, o.Description].join(" "),
    filters: [
      { id: "domaine", label: "Domaine", options: DOMAINES.map((d) => ({ value: d, label: d })), test: (r, v) => r.Domaine === v },
      { id: "statut", label: "Statut", options: [{ value: "Ouverte", label: "Ouverte" }, { value: "Clôturée", label: "Clôturée" }],
        test: (r, v) => (r.Statut || "Ouverte") === v },
    ],
  });
}

const renderOffres = () => safe(async () => { CACHE.offres = await Api.listOffres(); TABLES.offres.setRows(CACHE.offres); });
const findOffre = (id) => CACHE.offres.find((o) => o.ID === id);

function detailOffre(id) {
  const o = findOffre(id);
  const lignes = [
    ["Domaine", badge(o.Domaine)], ["Entreprise", escapeHtml(o.Entreprise)], ["Lieu", escapeHtml(o.Lieu)],
    ["Rythme", escapeHtml(o.Rythme)], ["Durée", escapeHtml(o.Duree)],
    ["Date limite", o.DateLimite ? fmtDate(o.DateLimite) : ""], ["Statut", badgeStatutOffre(o)],
    ["Publiée le", fmtDateTime(o.CreeLe)],
  ].filter(([, v]) => v);
  const actions = [];
  if (o.FichierKey || safeUrl(o.URL)) actions.push(btn("Ouvrir le fichier / lien", "offre-fichier", id));
  if (ME.role === "etudiant" && !o.DejaPostule && (o.Statut || "Ouverte") === "Ouverte" && !offreExpiree(o))
    actions.push(btn("Postuler", "offre-postuler", id, "btn-primary"));
  if (isStaff()) {
    actions.push(btn("Renvoyer l'alerte", "offre-notifier", id));
    actions.push(btn("Supprimer", "offre-supprimer", id, "btn-secondary btn-danger"));
  }
  openModal(titreOffre(o), `
    <dl class="detail-list">${lignes.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join("")}</dl>
    ${o.Description ? `<div class="detail-text">${escapeHtml(o.Description)}</div>` : ""}
    <div class="form-actions" style="justify-content:flex-start">${actions.join("")}</div>`, true);
}

function formOffre(o = null) {
  const v = (k) => escapeHtml(o?.[k] ?? "");
  openModal(o ? "Modifier l'offre" : "Nouvelle offre", `
    <div class="field"><label>Titre *</label><input id="f-titre" maxlength="150" value="${escapeHtml(o ? titreOffre(o) : "")}" placeholder="Ex : Développeur Cloud en alternance" /></div>
    <div class="grid-2">
      <div class="field"><label>Domaine *</label><select id="f-domaine">
        ${DOMAINES.map((d) => `<option ${o?.Domaine === d ? "selected" : ""}>${escapeHtml(d)}</option>`).join("")}</select></div>
      <div class="field"><label>Entreprise</label><input id="f-entreprise" maxlength="100" value="${v("Entreprise")}" /></div>
      <div class="field"><label>Lieu</label><input id="f-lieu" maxlength="100" value="${v("Lieu")}" /></div>
      <div class="field"><label>Rythme</label><input id="f-rythme" maxlength="80" value="${v("Rythme")}" placeholder="Ex : 3 jours / 2 jours" /></div>
      <div class="field"><label>Durée</label><input id="f-duree" maxlength="50" value="${v("Duree")}" placeholder="Ex : 12 mois" /></div>
      <div class="field"><label>Date limite</label><input id="f-limite" type="date" value="${v("DateLimite")}" /></div>
    </div>
    <div class="field"><label>Lien (optionnel)</label><input id="f-url" maxlength="500" value="${v("URL")}" placeholder="https://…" /></div>
    <div class="field"><label>Description</label><textarea id="f-desc" rows="4" maxlength="4000">${v("Description")}</textarea></div>
    ${o ? "" : `<div class="field-check"><input type="checkbox" id="f-notifier" checked /><label for="f-notifier" style="margin:0;font-weight:400">Alerter par email les étudiants du domaine</label></div>`}
    <div class="form-actions">
      <button class="btn-secondary" data-action="modal-close">Annuler</button>
      <button class="btn-primary" data-action="offre-submit" data-id="${o ? escapeHtml(o.ID) : ""}">${o ? "Enregistrer" : "Publier"}</button>
    </div>`, true);
}

async function submitOffre({ id }) {
  const val = (i) => document.getElementById(i).value;
  const payload = {
    titre: val("f-titre"), domaine: val("f-domaine"), entreprise: val("f-entreprise"), lieu: val("f-lieu"),
    rythme: val("f-rythme"), duree: val("f-duree"), date_limite: val("f-limite"), url: val("f-url"), description: val("f-desc"),
  };
  if (id) await Api.modifierOffre(id, payload);
  else {
    payload.notifier = document.getElementById("f-notifier").checked;
    const r = await Api.creerOffre(payload);
    toast(r.notifies != null ? `Offre publiée, alerte envoyée (${r.notifies} étudiant(s) du domaine)` : "Offre publiée");
  }
  if (id) toast("Offre mise à jour");
  closeModal();
  renderOffres();
}

async function ouvrirFichier(id) {
  const w = window.open("", "_blank"); // ouvert avant l'await pour éviter le blocage popup
  try {
    const { url } = await Api.fichierOffre(id);
    const u = safeUrl(url);
    if (!u) throw new Error("Lien invalide");
    w.location.href = u;
  } catch (e) { w?.close(); throw e; }
}

// ---- Postuler (avec CV / lettre) ----

function formPostuler(id) {
  const o = findOffre(id);
  openModal(`Postuler : ${titreOffre(o)}`, `
    <div class="field"><label>Message (optionnel)</label><textarea id="p-msg" rows="4" maxlength="2000" placeholder="Quelques mots sur votre motivation…"></textarea></div>
    <div class="field"><label>CV</label><input type="file" id="p-cv" accept=".pdf,.doc,.docx" /><div class="hint">PDF, DOC ou DOCX — 5 Mo maximum</div></div>
    <div class="field"><label>Lettre de motivation (optionnel)</label><input type="file" id="p-lettre" accept=".pdf,.doc,.docx" /></div>
    <div class="form-actions">
      <button class="btn-secondary" data-action="modal-close">Annuler</button>
      <button class="btn-primary" data-action="postuler-submit" data-id="${escapeHtml(id)}">Envoyer ma candidature</button>
    </div>`, true);
}

function typeMime(file) {
  if (Object.values(TYPES_FICHIER).includes(file.type)) return file.type;
  return TYPES_FICHIER[(file.name.split(".").pop() || "").toLowerCase()] || null;
}

async function envoyerDocument(file, type) {
  const contentType = typeMime(file);
  if (!contentType) throw new Error("Format refusé : PDF, DOC ou DOCX uniquement");
  if (file.size > TAILLE_MAX) throw new Error("Fichier trop volumineux (5 Mo maximum)");
  const up = await Api.uploadUrl({ type, filename: file.name, contentType });
  const fd = new FormData();
  Object.entries(up.fields).forEach(([k, v]) => fd.append(k, v));
  fd.append("file", file); // le fichier doit être le dernier champ
  const r = await fetch(up.url, { method: "POST", body: fd });
  if (!r.ok) throw new Error("Échec de l'envoi du document");
  return up.key;
}

async function submitPostuler({ id }) {
  const cv = document.getElementById("p-cv").files[0];
  const lettre = document.getElementById("p-lettre").files[0];
  const payload = { offreId: id, message: document.getElementById("p-msg").value };
  if (cv) payload.cvKey = await envoyerDocument(cv, "cv");
  if (lettre) payload.lettreKey = await envoyerDocument(lettre, "lettre");
  await Api.postuler(payload);
  closeModal();
  toast("Candidature envoyée");
  renderOffres();
}

// ---------------------------------------------------------------------
// ÉTUDIANTS
// ---------------------------------------------------------------------

function initTableEtudiants() {
  TABLES.etudiants = new DataTable("etudiants-table", {
    defaultSort: { key: "nom", dir: "asc" }, empty: "Aucun étudiant enregistré.",
    searchText: (e) => `${e.Nom} ${e.Email}`,
    filters: [{ id: "domaine", label: "Domaine", options: DOMAINES.map((d) => ({ value: d, label: d })),
      test: (r, v) => (r.Domaines || []).includes(v) }],
    columns: [
      { key: "nom", label: "Étudiant", sort: (e) => (e.Nom || "").toLowerCase(),
        html: (e) => `<div class="cell-title">${escapeHtml(e.Nom)}</div><div class="cell-sub">${escapeHtml(e.Email)}</div>` },
      { key: "domaines", label: "Domaines suivis",
        html: (e) => `<div class="badge-list">${(e.Domaines || []).map((d) => badge(d)).join("")}</div>` },
      { key: "ajout", label: "Ajouté le", sort: (e) => e.DateAjout || "", html: (e) => fmtDate(e.DateAjout) },
      { key: "actions", label: "", html: (e) => `<div class="row-actions">${btn("Candidatures", "etudiant-detail", e.Email)}${btn("Retirer", "etudiant-supprimer", e.Email, "btn-secondary btn-danger")}</div>` },
    ],
  });
}

const renderEtudiants = () => safe(async () => { CACHE.etudiants = await Api.listEtudiants(); TABLES.etudiants.setRows(CACHE.etudiants); });

function cochesDomaines(selection = []) {
  return DOMAINES.map((d) => {
    const auto = d === "General";
    return `<div class="field-check"><input type="checkbox" value="${escapeHtml(d)}" id="d-${escapeHtml(d)}"
      ${auto || selection.includes(d) ? "checked" : ""} ${auto ? "disabled" : ""} />
      <label for="d-${escapeHtml(d)}" style="margin:0;font-weight:400">${escapeHtml(d)}${auto ? " (toujours inclus)" : ""}</label></div>`;
  }).join("");
}
const domainesCoches = () => DOMAINES.filter((d) => document.getElementById(`d-${d}`)?.checked && d !== "General");

function formEtudiant() {
  openModal("Ajouter un étudiant", `
    <div class="field"><label>Email *</label><input id="e-email" type="email" placeholder="prenom.nom@ecole.com" /></div>
    <div class="field"><label>Nom</label><input id="e-nom" maxlength="100" placeholder="Déduit de l'email si vide" /></div>
    <div class="field"><label>Domaines suivis</label>${cochesDomaines()}</div>
    <p class="hint muted small">L'étudiant reçoit un email Cognito (mot de passe temporaire) et un email de confirmation AWS par domaine.</p>
    <div class="form-actions">
      <button class="btn-secondary" data-action="modal-close">Annuler</button>
      <button class="btn-primary" data-action="etudiant-submit">Ajouter</button>
    </div>`);
}

async function submitEtudiant() {
  await Api.creerEtudiant({ email: document.getElementById("e-email").value, nom: document.getElementById("e-nom").value, domaines: domainesCoches() });
  closeModal(); toast("Étudiant ajouté"); renderEtudiants();
}

async function detailEtudiant(email) {
  const e = CACHE.etudiants.find((x) => x.Email === email);
  openModal(`${e?.Nom || email}`, `<p class="muted">Chargement…</p>`, true);
  const cands = (await Api.listCandidatures()).filter((c) => c.EtudiantEmail === email);
  document.getElementById("modal-body").innerHTML = `
    <p class="muted small">${escapeHtml(email)}</p>
    ${cands.length ? `<table><thead><tr><th>Offre</th><th>Date</th><th>Statut</th></tr></thead><tbody>
      ${cands.map((c) => `<tr><td>${escapeHtml(c.OffreTitre)}<div class="cell-sub">${escapeHtml(c.OffreEntreprise)}</div></td>
        <td>${fmtDate(c.DateCandidature)}</td><td>${badgeStatutCand(c.Statut)}</td></tr>`).join("")}</tbody></table>`
      : `<div class="empty-state">Aucune candidature.</div>`}`;
}

async function supprimerEtudiant({ id }) {
  if (!confirm(`Supprimer définitivement ${id} ?\n\nCela efface aussi ses candidatures, ses CV et lettres, ses abonnements aux alertes et son compte de connexion. Action irréversible.`)) return;
  const r = await Api.supprimerEtudiant(id);
  toast(`Étudiant supprimé (${r.candidatures_supprimees} candidature(s) purgée(s))`);
  renderEtudiants();
}

function formStaff() {
  openModal("Créer un compte admin / recruteur", `
    <div class="field"><label>Email *</label><input id="s-email" type="email" /></div>
    <div class="field"><label>Rôle</label><select id="s-role">
      <option value="Recruteurs">Recruteur (publie et gère ses propres offres)</option>
      <option value="Admins">Administrateur (accès complet)</option></select></div>
    <p class="hint muted small">La personne reçoit un email avec un mot de passe temporaire.</p>
    <div class="form-actions">
      <button class="btn-secondary" data-action="modal-close">Annuler</button>
      <button class="btn-primary" data-action="staff-submit">Créer le compte</button>
    </div>`);
}

async function submitStaff() {
  await Api.creerCompteStaff(document.getElementById("s-email").value, document.getElementById("s-role").value);
  closeModal(); toast("Compte créé, un email a été envoyé");
}

async function importerCsv(file) {
  const { etudiants, rejets } = grouperImport(parseCsv(await file.text()), DOMAINES);
  if (!etudiants.length) return toast("Aucun étudiant valide dans ce fichier", "error");
  if (!confirm(`Importer ${etudiants.length} étudiant(s) ?${rejets.length ? `\n${rejets.length} ligne(s) ignorée(s).` : ""}\n\nChacun recevra des emails de confirmation.`)) return;

  openModal("Import en cours", `<p id="import-progress" class="muted">Préparation…</p>`);
  let crees = 0;
  const problemes = [...rejets];
  try {
    for (let i = 0; i < etudiants.length; i += 20) { // lots de 20 : 1 étudiant = plusieurs appels AWS
      document.getElementById("import-progress").textContent = `${Math.min(i + 20, etudiants.length)} / ${etudiants.length}…`;
      const r = await Api.importerEtudiants(etudiants.slice(i, i + 20));
      crees += r.crees;
      r.erreurs.forEach((x) => problemes.push(`${x.email} : ${x.erreur}`));
    }
  } catch (e) { problemes.push(`Import interrompu : ${e.message}`); }
  document.getElementById("modal-title").textContent = "Import terminé";
  document.getElementById("modal-body").innerHTML = `
    <p><strong>${crees}</strong> étudiant(s) importé(s).</p>
    ${problemes.length ? `<p class="small muted">${problemes.length} point(s) à vérifier :</p>
      <ul class="result-list">${problemes.map((p) => `<li>${escapeHtml(p)}</li>`).join("")}</ul>` : ""}
    <div class="form-actions"><button class="btn-primary" data-action="modal-close">Fermer</button></div>`;
  renderEtudiants();
}

// ---------------------------------------------------------------------
// CANDIDATURES
// ---------------------------------------------------------------------

function initTableCandidatures() {
  const cols = [
    { key: "offre", label: "Offre", sort: (c) => (c.OffreTitre || "").toLowerCase(),
      html: (c) => `<div class="cell-title">${escapeHtml(c.OffreTitre)}</div><div class="cell-sub">${escapeHtml(c.OffreEntreprise)}</div>` },
    { key: "domaine", label: "Domaine", sort: (c) => c.OffreDomaine || "", html: (c) => c.OffreDomaine ? badge(c.OffreDomaine) : "—" },
    { key: "date", label: "Candidature", sort: (c) => c.DateCandidature || "", html: (c) => fmtDate(c.DateCandidature) },
    { key: "statut", label: "Statut", sort: (c) => STATUTS.indexOf(c.Statut),
      html: (c) => isStaff()
        ? `<select data-change="cand-statut" data-id="${escapeHtml(c.ID)}">${STATUTS.map((s) => `<option ${s === c.Statut ? "selected" : ""}>${s}</option>`).join("")}</select>`
        : badgeStatutCand(c.Statut) },
    { key: "docs", label: "Documents", html: (c) => `<div class="badge-list">${c.HasCv ? badge("CV", "doc") : ""}${c.HasLettre ? badge("Lettre", "doc") : ""}${!c.HasCv && !c.HasLettre ? "—" : ""}</div>` },
    { key: "actions", label: "", html: (c) => btn("Détail", "cand-detail", c.ID) },
  ];
  if (isStaff()) cols.unshift({ key: "etudiant", label: "Étudiant", sort: (c) => (c.EtudiantNom || c.EtudiantEmail).toLowerCase(),
    html: (c) => `<div class="cell-title">${escapeHtml(c.EtudiantNom)}</div><div class="cell-sub">${escapeHtml(c.EtudiantEmail)}</div>` });

  TABLES.cands = new DataTable("candidatures-table", {
    columns: cols, defaultSort: { key: "date", dir: "desc" }, empty: "Aucune candidature.",
    searchText: (c) => [c.EtudiantNom, c.EtudiantEmail, c.OffreTitre, c.OffreEntreprise].join(" "),
    filters: [
      { id: "statut", label: "Statut", options: STATUTS.map((s) => ({ value: s, label: s })), test: (r, v) => r.Statut === v },
      { id: "domaine", label: "Domaine", options: DOMAINES.map((d) => ({ value: d, label: d })), test: (r, v) => r.OffreDomaine === v },
    ],
  });
}

const renderCandidatures = () => safe(async () => { CACHE.cands = await Api.listCandidatures(); TABLES.cands.setRows(CACHE.cands); });

async function changerStatut(id, statut) {
  await Api.majCandidature(id, { statut });
  toast("Statut mis à jour, l'étudiant est prévenu par email");
  renderCandidatures();
}

async function detailCandidature(id) {
  const c = CACHE.cands.find((x) => x.ID === id);
  const lignes = [
    ["Étudiant", `${escapeHtml(c.EtudiantNom)} <span class="muted">(${escapeHtml(c.EtudiantEmail)})</span>`],
    ["Offre", escapeHtml(c.OffreTitre)], ["Statut", badgeStatutCand(c.Statut)],
    ["Candidature", fmtDateTime(c.DateCandidature)], ["Dernière mise à jour", fmtDateTime(c.DateMaj)],
    ["Décision", c.DateDecision ? fmtDateTime(c.DateDecision) : ""],
  ].filter(([, v]) => v);
  openModal("Candidature", `
    <dl class="detail-list">${lignes.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join("")}</dl>
    <div id="cand-docs"><p class="muted small">Chargement du message et des documents…</p></div>
    ${isStaff() ? `<div class="field"><label>Notes internes (invisibles pour l'étudiant)</label>
      <textarea id="cand-notes" rows="4" maxlength="4000">${escapeHtml(c.NotesInternes || "")}</textarea></div>
      <div class="form-actions"><button class="btn-primary" data-action="cand-notes-save" data-id="${escapeHtml(id)}">Enregistrer les notes</button></div>` : ""}`, true);

  const d = await Api.documents(id);
  const liens = [d.cv && ["CV", d.cv], d.lettre && ["Lettre de motivation", d.lettre]].filter(Boolean);
  document.getElementById("cand-docs").innerHTML = `
    ${d.message ? `<div class="detail-text">${escapeHtml(d.message)}</div>` : ""}
    ${liens.length ? `<div class="doc-links">${liens.map(([l, u]) => `<a href="${escapeHtml(safeUrl(u))}" target="_blank" rel="noopener">${l} ↗</a>`).join("")}</div>`
      : `<p class="muted small">Aucun document joint.</p>`}`;
}

function exporterCandidatures() {
  const lignes = TABLES.cands.getFiltered().map((c) => [
    c.EtudiantNom, c.EtudiantEmail, c.OffreTitre, c.OffreEntreprise, c.OffreDomaine,
    (c.DateCandidature || "").slice(0, 10), c.Statut, c.HasCv ? "oui" : "non", c.HasLettre ? "oui" : "non", c.NotesInternes || "",
  ]);
  telechargerCsv(`candidatures-${aujourdhui()}.csv`,
    toCsv(["Nom", "Email", "Offre", "Entreprise", "Domaine", "Date", "Statut", "CV", "Lettre", "Notes internes"], lignes));
  toast(`${lignes.length} candidature(s) exportée(s) (filtres appliqués)`);
}

// ---------------------------------------------------------------------
// NOTIFICATIONS / AUDIT
// ---------------------------------------------------------------------

function initTablesAdmin() {
  TABLES.notifs = new DataTable("notifications-table", {
    defaultSort: { key: "date", dir: "desc" }, empty: "Aucun envoi enregistré.",
    searchText: (n) => `${n.Titre} ${n.Domaine} ${n.Acteur}`,
    filters: [{ id: "type", label: "Type", options: Object.entries(TYPES_NOTIF).map(([value, label]) => ({ value, label })), test: (r, v) => r.Type === v }],
    columns: [
      { key: "date", label: "Date", sort: (n) => n.Date, html: (n) => fmtDateTime(n.Date) },
      { key: "type", label: "Type", sort: (n) => n.Type, html: (n) => badge(TYPES_NOTIF[n.Type] || n.Type, "info") },
      { key: "titre", label: "Objet", sort: (n) => n.Titre || "", html: (n) => escapeHtml(n.Titre) },
      { key: "domaine", label: "Domaine", html: (n) => n.Domaine ? badge(n.Domaine) : "—" },
      { key: "dest", label: "Destinataires", sort: (n) => n.Destinataires || 0, html: (n) => n.Destinataires ?? 0 },
      { key: "acteur", label: "Déclenché par", html: (n) => `<span class="muted">${escapeHtml(n.Acteur)}</span>` },
    ],
  });
  TABLES.audit = new DataTable("audit-table", {
    defaultSort: { key: "date", dir: "desc" }, empty: "Journal vide.", pageSize: 25,
    searchText: (a) => `${a.Acteur} ${a.Action} ${a.Cible} ${a.Details}`,
    columns: [
      { key: "date", label: "Date", sort: (a) => a.Date, html: (a) => fmtDateTime(a.Date) },
      { key: "acteur", label: "Acteur", sort: (a) => a.Acteur, html: (a) => escapeHtml(a.Acteur) },
      { key: "action", label: "Action", sort: (a) => a.Action, html: (a) => badge(a.Action, "info") },
      { key: "cible", label: "Cible", html: (a) => `<span class="muted small">${escapeHtml(a.Cible)}</span>` },
      { key: "details", label: "Détails", html: (a) => escapeHtml(a.Details) },
    ],
  });
}

const renderNotifications = () => safe(async () => TABLES.notifs.setRows(await Api.notifications()));
const renderAudit = () => safe(async () => TABLES.audit.setRows(await Api.audit()));

// ---------------------------------------------------------------------
// STATISTIQUES
// ---------------------------------------------------------------------

function barres(titre, donnees, ordre = null, couleur = "") {
  const entrees = ordre ? ordre.map((k) => [k, donnees[k] || 0])
    : Object.entries(donnees).sort((a, b) => b[1] - a[1]);
  const max = Math.max(1, ...entrees.map((e) => e[1]));
  const corps = entrees.length ? entrees.map(([k, v]) => `
    <div class="bar-row"><span>${escapeHtml(k)}</span>
      <div class="bar-track"><div class="bar-fill ${couleur}" style="width:${(v / max) * 100}%"></div></div>
      <span class="bar-value">${v}</span></div>`).join("") : `<p class="muted small">Pas encore de données.</p>`;
  return `<div class="chart"><h3>${escapeHtml(titre)}</h3>${corps}</div>`;
}

const renderStats = () => safe(async () => {
  const s = await Api.stats();
  const carte = (v, l, h = "") => `<div class="stat-card"><div class="stat-value">${v}</div><div class="stat-label">${l}</div>${h ? `<div class="stat-hint">${h}</div>` : ""}</div>`;
  document.getElementById("stats-content").innerHTML = `
    <div class="stats-grid">
      ${carte(`${s.offres_ouvertes}<span class="muted" style="font-size:1.1rem"> / ${s.total_offres}</span>`, "Offres ouvertes")}
      ${carte(s.total_etudiants, "Étudiants suivis")}
      ${carte(s.total_candidatures, "Candidatures reçues")}
      ${carte(s.taux_acceptation == null ? "—" : `${s.taux_acceptation} %`, "Taux d'acceptation", "acceptées / candidatures décidées")}
      ${carte(s.delai_moyen_jours == null ? "—" : `${s.delai_moyen_jours} j`, "Délai moyen de traitement", "candidature → décision")}
      ${carte(s.nb_offres_sans_candidature, "Offres sans candidature", "offres ouvertes")}
    </div>
    <div class="charts">
      ${barres("Candidatures par statut", s.candidatures_par_statut, STATUTS)}
      ${barres("Candidatures par domaine", s.candidatures_par_domaine, null, "amber")}
      ${barres("Offres par domaine", s.offres_par_domaine)}
    </div>
    ${s.offres_sans_candidature.length ? `<div class="sans-cand"><h3>Offres ouvertes sans candidature</h3><ul>
      ${s.offres_sans_candidature.map((o) => `<li>${escapeHtml(o.Titre)} ${badge(o.Domaine)}</li>`).join("")}</ul>
      ${s.nb_offres_sans_candidature > s.offres_sans_candidature.length ? `<p class="muted small">… et ${s.nb_offres_sans_candidature - s.offres_sans_candidature.length} autre(s)</p>` : ""}</div>` : ""}`;
});

// ---------------------------------------------------------------------
// PROFIL ÉTUDIANT
// ---------------------------------------------------------------------

function renderProfil() {
  const box = document.getElementById("profil-content");
  if (!ME.profil) {
    box.innerHTML = `<p class="muted">Votre profil n'est pas encore enregistré. Contactez un administrateur.</p>`;
    return;
  }
  box.innerHTML = `
    <div class="field"><label>Email</label><input value="${escapeHtml(ME.email)}" disabled /></div>
    <div class="field"><label>Nom</label><input id="pr-nom" maxlength="100" value="${escapeHtml(ME.profil.Nom)}" /></div>
    <div class="field"><label>Domaines suivis</label>${cochesDomaines(ME.profil.Domaines || [])}</div>
    <p class="hint muted small">Chaque nouveau domaine déclenche un email de confirmation AWS : cliquez sur le lien pour recevoir les alertes.</p>
    <div class="form-actions" style="justify-content:flex-start"><button class="btn-primary" data-action="profil-save">Enregistrer</button></div>`;
}

async function saveProfil() {
  const r = await Api.majProfil({ nom: document.getElementById("pr-nom").value, domaines: domainesCoches() });
  ME.profil = { ...ME.profil, Nom: document.getElementById("pr-nom").value || ME.profil.Nom, Domaines: r.domaines };
  toast("Profil mis à jour");
}

// ---------------------------------------------------------------------
// Délégation d'événements
// ---------------------------------------------------------------------

const ACTIONS = {
  "modal-close": closeModal,
  "offre-nouvelle": () => formOffre(),
  "offre-modifier": ({ id }) => formOffre(findOffre(id)),
  "offre-detail": ({ id }) => detailOffre(id),
  "offre-postuler": ({ id }) => formPostuler(id),
  "offre-submit": submitOffre,
  "postuler-submit": submitPostuler,
  "offre-fichier": ({ id }) => ouvrirFichier(id),
  "offre-basculer": async ({ id }) => {
    const ferme = (findOffre(id).Statut || "Ouverte") === "Clôturée";
    await Api.modifierOffre(id, { statut: ferme ? "Ouverte" : "Clôturée" });
    toast(ferme ? "Offre rouverte" : "Offre clôturée");
    renderOffres();
  },
  "offre-notifier": async ({ id }) => {
    const r = await Api.notifier(id);
    toast(`Alerte renvoyée (${r.destinataires} étudiant(s) du domaine ${r.domaine})`);
  },
  "offre-supprimer": async ({ id }) => {
    if (!confirm("Supprimer cette offre ? Les candidatures déjà reçues sont conservées.")) return;
    await Api.supprimerOffre(id);
    closeModal(); toast("Offre supprimée"); renderOffres();
  },
  "etudiant-ajouter": formEtudiant,
  "etudiant-submit": submitEtudiant,
  "etudiant-import": () => document.getElementById("csv-file").click(),
  "etudiant-detail": ({ id }) => detailEtudiant(id),
  "etudiant-supprimer": supprimerEtudiant,
  "staff-creer": formStaff,
  "staff-submit": submitStaff,
  "cand-detail": ({ id }) => detailCandidature(id),
  "cand-notes-save": async ({ id }) => {
    await Api.majCandidature(id, { notes: document.getElementById("cand-notes").value });
    toast("Notes enregistrées"); renderCandidatures();
  },
  "cand-export": exporterCandidatures,
  "profil-save": saveProfil,
};

document.addEventListener("click", async (e) => {
  const el = e.target.closest("[data-action]");
  if (!el || el.disabled) return;
  const fn = ACTIONS[el.dataset.action];
  if (!fn) return;
  el.disabled = true;
  try { await fn(el.dataset, el); } catch (err) { toast(err.message, "error"); } finally { el.disabled = false; }
});

document.addEventListener("change", async (e) => {
  const el = e.target.closest("[data-change]");
  if (el?.dataset.change === "cand-statut") await safe(() => changerStatut(el.dataset.id, el.value)).then(() => null);
});

document.querySelectorAll(".nav-item").forEach((b) => b.addEventListener("click", () => showView(b.dataset.view)));
document.getElementById("btn-logout").addEventListener("click", () => Auth.logout());
document.getElementById("modal").addEventListener("click", (e) => { if (e.target.id === "modal") closeModal(); });
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeModal(); });
document.getElementById("csv-file").addEventListener("change", (e) => {
  const file = e.target.files[0];
  e.target.value = "";
  if (file) safe(() => importerCsv(file));
});

// ---------------------------------------------------------------------
// Démarrage
// ---------------------------------------------------------------------

(async function init() {
  let claims;
  try { claims = await Auth.ensureAuthenticated(); } catch (e) { window.location.href = "login.html?error=1"; return; }
  if (!claims) return; // redirection vers login en cours

  const me = await safe(() => Api.me());
  if (!me) return;
  Object.assign(ME, { role: me.role, email: me.email, profil: me.profil || null });
  DOMAINES = me.domaines_disponibles || [];

  document.getElementById("user-email").textContent = me.email;
  document.getElementById("user-role").textContent = { admin: "Administrateur", recruteur: "Recruteur", etudiant: "Étudiant" }[me.role] || "Sans rôle";
  if (me.role === "inconnu") {
    document.querySelector(".content").innerHTML = `<p class="muted">Aucun rôle n'est attribué à votre compte. Contactez un administrateur.</p>`;
    return;
  }

  document.getElementById("offres-sub").textContent = { admin: "Toutes les offres publiées.", recruteur: "Vos offres.", etudiant: "Offres publiées : consultez et postulez." }[me.role];
  document.getElementById("candidatures-sub").textContent = { admin: "Toutes les candidatures reçues.", recruteur: "Candidatures reçues sur vos offres.", etudiant: "Suivi de vos candidatures." }[me.role];

  applyRoles();
  initTableOffres(); initTableCandidatures();
  if (me.role === "admin") { initTableEtudiants(); initTablesAdmin(); }
  showView("offres");
})();
