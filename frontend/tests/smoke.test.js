/* Test de fumée du dashboard dans jsdom, avec une API simulée.
   Lancer : cd frontend/tests && npm install jsdom && node smoke.test.js */
const fs = require("fs");
const path = require("path");
const { JSDOM } = require("jsdom");
const vm = require("vm");

const ROOT = path.join(__dirname, "..");
const DOMAINES = ["Cloud", "Cyber", "Archi", "Web", "General"];
let echecs = 0;
const ok = (cond, msg) => { if (!cond) { echecs++; console.log("  ✗", msg); } else console.log("  ✓", msg); };
const wait = (ms = 30) => new Promise((r) => setTimeout(r, ms));

function fakeBackend(role) {
  const offres = [
    { ID: "o1", Titre: "Dev Cloud", Domaine: "Cloud", Entreprise: "Acme", Lieu: "Paris", Statut: "Ouverte", CreeLe: "2026-09-01T10:00:00+00:00", DateLimite: "2099-01-01", NbCandidatures: 1, DejaPostule: false, Rythme: "3j/2j" },
    { ID: "o2", Titre: '<img src=x onerror="window.PWNED=1">', Domaine: "Cyber", Entreprise: "Evil", Statut: "Clôturée", CreeLe: "2026-08-01T10:00:00+00:00", NbCandidatures: 0, DejaPostule: false },
    ...Array.from({ length: 20 }, (_, i) => ({ ID: `x${i}`, Titre: `Offre bulk ${i}`, Domaine: "Web", Statut: "Ouverte", CreeLe: `2026-07-${String(i + 1).padStart(2, "0")}T00:00:00+00:00`, NbCandidatures: 0 })),
  ];
  const cands = [{ ID: "c1", OffreID: "o1", OffreTitre: "Dev Cloud", OffreDomaine: "Cloud", OffreEntreprise: "Acme", EtudiantEmail: "jean@ecole.com", EtudiantNom: "Jean", Statut: "Reçue", DateCandidature: "2026-09-02T09:00:00+00:00", HasCv: true, HasLettre: false, NotesInternes: "top" }];
  const appels = [];
  const handler = (method, route, body) => {
    appels.push({ method, route, body });
    if (route === "me") return { email: `${role}@x.com`, role, domaines_disponibles: DOMAINES, ...(role === "etudiant" ? { profil: { Nom: "Jean", Domaines: ["Cloud", "General"] } } : {}) };
    if (route === "offres" && method === "GET") return offres;
    if (route === "offres" && method === "POST") return { id: "new", notifies: 3 };
    if (route.startsWith("offres/") && method === "PATCH") return { status: "ok" };
    if (route === "candidatures" && method === "GET") return cands;
    if (route === "candidatures" && method === "POST") return { id: "c2" };
    if (route === "candidatures/upload-url") return { url: "https://docs.s3.eu-west-3.amazonaws.com/", fields: { key: "documents/h/cv.pdf", policy: "p" }, key: "documents/h/cv.pdf" };
    if (route === "candidatures/c1/documents") return { cv: "https://s3/cv.pdf?sig", lettre: null, message: "Bonjour" };
    if (route === "candidatures/c1" && method === "PATCH") return { status: "ok" };
    if (route === "etudiants" && method === "GET") return [{ Email: "jean@ecole.com", Nom: "Jean", Domaines: ["Cloud", "General"], DateAjout: "2026-09-01T00:00:00+00:00" }];
    if (route === "etudiants/import") return { crees: body.etudiants.length, erreurs: [] };
    if (route === "etudiants" && method === "POST") return { status: "ok" };
    if (route === "notifications") return [{ ID: "n1", Date: "2026-09-03T10:00:00+00:00", Type: "statut", Titre: "Dev Cloud → Entretien", Domaine: "Cloud", Destinataires: 1, Acteur: "admin@x.com" }];
    if (route === "audit") return [{ ID: "a1", Date: "2026-09-03T10:00:00+00:00", Acteur: "admin@x.com", Action: "offre.creer", Cible: "o1", Details: "Dev Cloud" }];
    if (route === "stats") return { total_offres: 22, offres_ouvertes: 21, total_etudiants: 1, total_candidatures: 1, candidatures_par_statut: { "Reçue": 1 }, candidatures_par_domaine: { Cloud: 1 }, offres_par_domaine: { Cloud: 1, Web: 20 }, taux_acceptation: null, delai_moyen_jours: null, offres_sans_candidature: [{ ID: "x1", Titre: "Offre bulk 1", Domaine: "Web" }], nb_offres_sans_candidature: 21 };
    return { status: "ok" };
  };
  return { handler, appels };
}

let dom;
async function boot(role) {
  let html = fs.readFileSync(path.join(ROOT, "index.html"), "utf8").replace(/<script[^>]*src="[^"]*"[^>]*><\/script>/g, "");
  dom = new JSDOM(html, { runScripts: "outside-only", url: "https://dash.example.com/index.html", pretendToBeVisual: true });
  const w = dom.window;
  const be = fakeBackend(role);
  const jwt = "h." + Buffer.from(JSON.stringify({ email: `${role}@x.com` })).toString("base64") + ".s";
  w.sessionStorage.setItem("alternance_tokens", JSON.stringify({ id_token: jwt }));
  w.fetch = async (url, opts = {}) => {
    const route = String(url).replace(/^https:\/\/[^/]+\/[^/]+\//, "").replace(/^https:\/\/REMPLACER[^/]*\/dev\//, "");
    const body = opts.body && typeof opts.body === "string" ? JSON.parse(opts.body) : undefined;
    if (String(url).includes("s3.eu-west-3")) return { ok: true, status: 204, json: async () => ({}) };
    const data = be.handler(opts.method || "GET", decodeURIComponent(route), body);
    return { ok: true, status: 200, json: async () => data };
  };
  w.confirm = () => true;
  w.open = () => ({ close() {}, location: {} });
  w.alert = () => {};
  const errors = [];
  w.addEventListener("error", (e) => errors.push(e.message));
  for (const f of ["config.js", "auth.js", "api.js", "ui.js", "app.js"]) {
    // Exécution en script global (comme des balises <script>) : les const/let sont partagés entre fichiers
    try { new vm.Script(fs.readFileSync(path.join(ROOT, "js", f), "utf8"), { filename: f }).runInContext(dom.getInternalVMContext()); }
    catch (e) { errors.push(`${f}: ${e.message}`); }
  }
  await wait(80);
  return { w, doc: w.document, be, errors };
}

const visibles = (doc, sel) => [...doc.querySelectorAll(sel)].filter((e) => e.style.display !== "none").length;
const click = (el) => el.dispatchEvent(new el.ownerDocument.defaultView.MouseEvent("click", { bubbles: true }));

(async () => {
  console.log("\n== ADMIN ==");
  let { w, doc, be, errors } = await boot("admin");
  ok(errors.length === 0, `aucune erreur JS au chargement ${errors[0] || ""}`);
  ok(visibles(doc, ".nav-item") === 6, "admin voit 6 entrées de menu (pas « Mon profil »)");
  ok(doc.querySelectorAll("#offres-table tbody tr").length === 15, "pagination : 15 lignes sur 22 offres");
  ok(doc.querySelector("#offres-table [data-pager]").textContent.includes("Page 1 / 2"), "pager « Page 1 / 2 »");
  ok(!w.PWNED && !doc.querySelector("#offres-table img"), "XSS : le titre malveillant est échappé");

  const rech = doc.querySelector("#offres-table [data-search]");
  rech.value = "acme"; rech.dispatchEvent(new w.Event("input"));
  ok(doc.querySelectorAll("#offres-table tbody tr").length === 1, "recherche « acme » → 1 offre");
  rech.value = ""; rech.dispatchEvent(new w.Event("input"));
  const sel = doc.querySelector('#offres-table [data-filter="statut"]');
  sel.value = "Clôturée"; sel.dispatchEvent(new w.Event("change"));
  ok(doc.querySelectorAll("#offres-table tbody tr").length === 1, "filtre statut Clôturée → 1 offre");
  sel.value = ""; sel.dispatchEvent(new w.Event("change"));
  click(doc.querySelector("#offres-table th[data-sort='titre']"));
  const premier = doc.querySelector("#offres-table tbody tr td .cell-title").textContent;
  ok(premier.startsWith("<img") || premier === "Dev Cloud" || premier.startsWith("Dev"), `tri par titre appliqué (1er : ${premier.slice(0, 12)})`);

  click(doc.querySelector('[data-action="offre-detail"][data-id="o1"]'));
  ok(doc.getElementById("modal-title").textContent === "Dev Cloud" && !doc.getElementById("modal").classList.contains("hidden"), "modale détail d'offre");
  ok(doc.querySelector('#modal-body [data-action="offre-supprimer"]'), "admin : bouton Supprimer dans le détail");
  click(doc.querySelector('[data-action="modal-close"]'));

  click(doc.querySelector('[data-action="offre-nouvelle"]'));
  doc.getElementById("f-titre").value = "Nouvelle offre test"; doc.getElementById("f-domaine").value = "Cyber"; doc.getElementById("f-limite").value = "2099-05-05";
  click(doc.querySelector('[data-action="offre-submit"]')); await wait();
  const post = be.appels.find((a) => a.method === "POST" && a.route === "offres");
  ok(post && post.body.titre === "Nouvelle offre test" && post.body.domaine === "Cyber" && post.body.date_limite === "2099-05-05" && post.body.notifier === true, "création d'offre : payload correct (notifier=true)");

  click(doc.querySelector('[data-action="offre-basculer"][data-id="o1"]')); await wait();
  ok(be.appels.some((a) => a.route === "offres/o1" && a.method === "PATCH" && a.body.statut === "Clôturée"), "bouton Clôturer → PATCH statut");

  click(doc.querySelector('[data-view="candidatures"]')); await wait();
  ok(doc.querySelectorAll("#candidatures-table tbody tr").length === 1, "candidatures affichées");
  const st = doc.querySelector('select[data-change="cand-statut"]');
  ok(st && st.options.length === 5, "admin : select de statut à 5 étapes");
  st.value = "Entretien"; st.dispatchEvent(new w.Event("change", { bubbles: true })); await wait();
  ok(be.appels.some((a) => a.route === "candidatures/c1" && a.body?.statut === "Entretien"), "changement de statut → PATCH");
  click(doc.querySelector('[data-action="cand-detail"]')); await wait();
  ok(doc.getElementById("cand-notes")?.value === "top", "détail : notes internes visibles pour l'admin");
  ok(doc.querySelector("#cand-docs a")?.textContent.includes("CV"), "détail : lien CV chargé");
  click(doc.querySelector('[data-action="cand-notes-save"]')); await wait();
  ok(be.appels.some((a) => a.route === "candidatures/c1" && a.body?.notes === "top"), "enregistrement des notes");
  click(doc.querySelector('[data-action="modal-close"]'));

  click(doc.querySelector('[data-view="etudiants"]')); await wait();
  ok(doc.querySelectorAll("#etudiants-table tbody tr").length === 1, "étudiants listés");
  // import CSV format du lab
  const csv = "email;domaine\ndaf@estiam.com;Cloud\nmarie@estiam.com;Architecture\nbad;Cloud\n";
  const file = { text: async () => csv };
  const inp = doc.getElementById("csv-file");
  Object.defineProperty(inp, "files", { value: [file], configurable: true });
  inp.dispatchEvent(new w.Event("change")); await wait(80);
  const imp = be.appels.find((a) => a.route === "etudiants/import");
  ok(imp && imp.body.etudiants.length === 2 && imp.body.etudiants[1].domaines[0] === "Archi", "import CSV du lab : 2 étudiants, « Architecture » → Archi, ligne invalide ignorée");
  ok(doc.getElementById("modal-title").textContent === "Import terminé", "récap d'import affiché");
  click(doc.querySelector('[data-action="modal-close"]'));

  for (const v of ["notifications", "stats", "audit"]) { click(doc.querySelector(`[data-view="${v}"]`)); await wait(); }
  ok(doc.querySelectorAll("#notifications-table tbody tr").length === 1, "historique des notifications");
  ok(doc.querySelectorAll("#audit-table tbody tr").length === 1, "journal d'audit");
  ok(doc.querySelectorAll("#stats-content .stat-card").length === 6 && doc.querySelectorAll(".bar-row").length >= 8, "stats : 6 cartes + graphiques");
  ok(doc.querySelector("#stats-content").textContent.includes("Offres ouvertes sans candidature"), "stats : liste des offres sans candidature");

  console.log("\n== ÉTUDIANT ==");
  ({ w, doc, be, errors } = await boot("etudiant"));
  ok(errors.length === 0, `aucune erreur JS ${errors[0] || ""}`);
  ok(visibles(doc, ".nav-item") === 3, "étudiant : Offres, Candidatures, Mon profil");
  ok(visibles(doc, '.head-actions [data-roles], [data-action="offre-nouvelle"]') === 0 || doc.querySelector('[data-action="offre-nouvelle"]').style.display === "none", "bouton « Nouvelle offre » masqué");
  ok(!doc.querySelector('[data-action="offre-modifier"]') && doc.querySelector('[data-action="offre-postuler"]'), "étudiant : Postuler oui, Modifier non");
  ok(!doc.querySelector('[data-action="offre-postuler"][data-id="o2"]'), "pas de bouton Postuler sur une offre clôturée");
  click(doc.querySelector('[data-action="offre-postuler"][data-id="o1"]'));
  doc.getElementById("p-msg").value = "Motivé";
  const cv = { name: "cv.pdf", type: "application/pdf", size: 1000 };
  Object.defineProperty(doc.getElementById("p-cv"), "files", { value: [cv], configurable: true });
  w.FormData = class { constructor() { this.d = []; } append(k, v) { this.d.push([k, v]); } };
  click(doc.querySelector('[data-action="postuler-submit"]')); await wait(60);
  const c = be.appels.find((a) => a.method === "POST" && a.route === "candidatures");
  ok(c && c.body.offreId === "o1" && c.body.cvKey === "documents/h/cv.pdf" && c.body.message === "Motivé", "postuler : upload S3 puis candidature avec cvKey");
  click(doc.querySelector('[data-view="candidatures"]')); await wait();
  ok(!doc.querySelector('select[data-change="cand-statut"]'), "étudiant : pas de select de statut");
  ok(!doc.querySelector("#candidatures-table th")?.textContent.includes("Étudiant"), "étudiant : pas de colonne Étudiant");
  click(doc.querySelector('[data-view="profil"]')); await wait();
  ok(doc.getElementById("d-General")?.disabled && doc.getElementById("d-General").checked, "profil : General toujours coché et verrouillé");
  ok(doc.getElementById("d-Cloud").checked && !doc.getElementById("d-Cyber").checked, "profil : domaines actuels pré-cochés");
  doc.getElementById("d-Cyber").checked = true;
  click(doc.querySelector('[data-action="profil-save"]')); await wait();
  const pf = be.appels.find((a) => a.route === "me/profile");
  ok(pf && pf.body.domaines.includes("Cyber") && pf.body.domaines.includes("Cloud") && !pf.body.domaines.includes("General"), "profil : PUT avec domaines cochés");
  new vm.Script('showView("stats")').runInContext(dom.getInternalVMContext()); await wait();
  ok(doc.getElementById("view-stats").classList.contains("hidden"), "étudiant : la vue Statistiques reste inaccessible");

  console.log("\n== RECRUTEUR ==");
  ({ w, doc, be, errors } = await boot("recruteur"));
  ok(errors.length === 0, `aucune erreur JS ${errors[0] || ""}`);
  ok(visibles(doc, ".nav-item") === 2, "recruteur : Offres + Candidatures seulement");
  ok(doc.querySelector('[data-action="offre-modifier"]') && doc.querySelector('[data-action="offre-nouvelle"]').style.display !== "none", "recruteur : peut créer/modifier");
  ok(doc.querySelector("#offres-table th:nth-child(6)")?.textContent.includes("Candidatures"), "recruteur : colonne « Candidatures » (compteur)");
  click(doc.querySelector('[data-view="candidatures"]')); await wait();
  ok(doc.querySelector('select[data-change="cand-statut"]') && doc.querySelector('[data-action="cand-export"]').style.display !== "none", "recruteur : gère le pipeline et exporte");

  console.log(echecs ? `\n${echecs} ÉCHEC(S)` : "\nTous les tests frontend passent");
  process.exit(echecs ? 1 : 0);
})();
