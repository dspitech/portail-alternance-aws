/* Test de contrat : le frontend est exécuté sur les VRAIES réponses de la Lambda API
   (fixtures.json, généré par backend/tests/test_export_fixtures.py).
   Vérifie que chaque vue s'affiche sans erreur, avec le bon nombre de lignes. */
const fs = require("fs");
const path = require("path");
const vm = require("vm");
const { JSDOM } = require("jsdom");

const ROOT = path.join(__dirname, "..");
const FIX = JSON.parse(fs.readFileSync(path.join(__dirname, "fixtures.json"), "utf8"));
let echecs = 0;
const ok = (c, m) => { if (!c) { echecs++; console.log("  ✗", m); } else console.log("  ✓", m); };
const wait = (ms = 40) => new Promise((r) => setTimeout(r, ms));
const click = (el) => el.dispatchEvent(new el.ownerDocument.defaultView.MouseEvent("click", { bubbles: true }));

async function boot(role) {
  const html = fs.readFileSync(path.join(ROOT, "index.html"), "utf8").replace(/<script[^>]*src="[^"]*"[^>]*><\/script>/g, "");
  const dom = new JSDOM(html, { runScripts: "outside-only", url: "https://dash.example.com/index.html" });
  const w = dom.window, errors = [];
  const jwt = "h." + Buffer.from(JSON.stringify({ email: `${role}@x.com` })).toString("base64") + ".s";
  w.sessionStorage.setItem("alternance_tokens", JSON.stringify({ id_token: jwt }));
  w.fetch = async (url, opts = {}) => {
    const route = decodeURIComponent(String(url).replace(/^https:\/\/[^/]+\/[^/]+\//, ""));
    const data = (opts.method || "GET") === "GET" ? FIX[role][route] : { status: "ok" };
    if (data === undefined) { errors.push(`route non couverte par la vraie API : ${route}`); return { ok: false, status: 404, json: async () => ({ error: "404" }) }; }
    return { ok: true, status: 200, json: async () => data };
  };
  w.confirm = () => true; w.open = () => ({ close() {}, location: {} });
  for (const f of ["config.js", "auth.js", "api.js", "ui.js", "app.js"]) {
    try { new vm.Script(fs.readFileSync(path.join(ROOT, "js", f), "utf8"), { filename: f }).runInContext(dom.getInternalVMContext()); }
    catch (e) { errors.push(`${f}: ${e.message}`); }
  }
  await wait(100);
  return { w, doc: w.document, errors };
}

const rows = (doc, id) => doc.querySelectorAll(`#${id} tbody tr`).length;
const toastsErreur = (doc) => [...doc.querySelectorAll("#toasts .toast.error")].map((t) => t.textContent);

(async () => {
  console.log("\n== ADMIN sur réponses réelles ==");
  let { doc, errors } = await boot("admin");
  ok(rows(doc, "offres-table") === FIX.admin.offres.length, `offres : ${FIX.admin.offres.length} ligne(s)`);
  for (const [vue, table, cle] of [["candidatures", "candidatures-table", "candidatures"], ["etudiants", "etudiants-table", "etudiants"],
    ["notifications", "notifications-table", "notifications"], ["audit", "audit-table", "audit"]]) {
    click(doc.querySelector(`[data-view="${vue}"]`)); await wait();
    ok(rows(doc, table) === FIX.admin[cle].length && rows(doc, table) > 0, `${vue} : ${FIX.admin[cle].length} ligne(s) affichée(s)`);
  }
  click(doc.querySelector('[data-view="stats"]')); await wait();
  ok(doc.querySelectorAll("#stats-content .stat-card").length === 6, "stats : 6 cartes depuis la vraie réponse");
  ok(!doc.querySelector("#stats-content").textContent.includes("undefined") && !doc.querySelector("#stats-content").textContent.includes("NaN"), "stats : aucun « undefined » / « NaN »");
  click(doc.querySelector('[data-view="candidatures"]')); await wait();
  ok(doc.querySelector(".cell-title").textContent.length > 0 && doc.querySelector('#candidatures-table select[data-change="cand-statut"]'), "candidatures : nom + select de statut");
  const select = doc.querySelector('#candidatures-table select[data-change="cand-statut"]');
  ok(select.value === "Entretien", "candidatures : statut réel « Entretien » pré-sélectionné");
  click(doc.querySelector('[data-action="cand-detail"]')); await wait();
  ok(doc.getElementById("cand-notes")?.value === "Bon profil" && doc.querySelector("#cand-docs a"), "détail : notes + lien CV issus de la vraie API");
  ok(toastsErreur(doc).length === 0 && errors.length === 0, `aucune erreur ${[...errors, ...toastsErreur(doc)][0] || ""}`);

  console.log("\n== ÉTUDIANT sur réponses réelles ==");
  ({ doc, errors } = await boot("etudiant"));
  ok(rows(doc, "offres-table") === FIX.etudiant.offres.length, `offres : ${FIX.etudiant.offres.length} ligne(s)`);
  ok(doc.querySelector(`[data-action="offre-postuler"][data-id="${FIX.oid}"]`) === null, "offre déjà postulée : pas de bouton Postuler (DejaPostule réel)");
  ok(doc.querySelectorAll('[data-action="offre-postuler"]').length === 1, "l'autre offre (non postulée) garde son bouton Postuler");
  ok(doc.body.textContent.includes("Postulé"), "badge « Postulé » affiché");
  click(doc.querySelector('[data-view="candidatures"]')); await wait();
  ok(rows(doc, "candidatures-table") === 1, "candidatures : la sienne");
  ok(!doc.querySelector("#candidatures-table").textContent.includes("Bon profil"), "les notes internes n'apparaissent pas côté étudiant");
  click(doc.querySelector('[data-view="profil"]')); await wait();
  ok(doc.getElementById("d-Cloud")?.checked && doc.getElementById("d-General")?.disabled, "profil : domaines réels pré-cochés");
  ok(toastsErreur(doc).length === 0 && errors.length === 0, `aucune erreur ${[...errors, ...toastsErreur(doc)][0] || ""}`);

  console.log("\n== RECRUTEUR sur réponses réelles ==");
  ({ doc, errors } = await boot("recruteur"));
  ok(rows(doc, "offres-table") === 1 && doc.body.textContent.includes("Analyste SOC"), "recruteur : uniquement son offre");
  click(doc.querySelector('[data-view="candidatures"]')); await wait();
  ok(rows(doc, "candidatures-table") === 0, "recruteur : aucune candidature sur son offre");
  ok(toastsErreur(doc).length === 0 && errors.length === 0, `aucune erreur ${[...errors, ...toastsErreur(doc)][0] || ""}`);

  console.log(echecs ? `\n${echecs} ÉCHEC(S)` : "\nContrat frontend ↔ API respecté");
  process.exit(echecs ? 1 : 0);
})();
