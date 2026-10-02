/* Briques UI réutilisables : échappement, toasts, modale, CSV, tableau filtrable/triable/paginé. */

function escapeHtml(str) {
  return String(str ?? "").replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
}

/** N'autorise que http(s) : évite les liens javascript: */
function safeUrl(url) {
  return /^https?:\/\//i.test(url || "") ? url : "";
}

function fmtDate(iso) {
  if (!iso) return "—";
  const d = new Date(iso.length === 10 ? iso + "T00:00:00" : iso);
  return isNaN(d) ? escapeHtml(iso) : d.toLocaleDateString("fr-FR");
}

function fmtDateTime(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  return isNaN(d) ? escapeHtml(iso) : d.toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" });
}

// ---------------------------------------------------------------------
// Toasts et modale
// ---------------------------------------------------------------------

function toast(message, type = "ok") {
  const box = document.getElementById("toasts");
  if (!box) return;
  const el = document.createElement("div");
  el.className = `toast ${type}`;
  el.textContent = message;
  box.appendChild(el);
  setTimeout(() => el.remove(), type === "error" ? 6000 : 3500);
}

function openModal(title, bodyHtml, wide = false) {
  document.getElementById("modal-title").textContent = title;
  document.getElementById("modal-body").innerHTML = bodyHtml;
  document.querySelector("#modal .modal").classList.toggle("wide", wide);
  document.getElementById("modal").classList.remove("hidden");
}

function closeModal() {
  document.getElementById("modal").classList.add("hidden");
  document.getElementById("modal-body").innerHTML = "";
}

// ---------------------------------------------------------------------
// CSV
// ---------------------------------------------------------------------

function parseCsv(text) {
  text = text.replace(/^\uFEFF/, "");
  const first = text.split(/\r?\n/)[0] || "";
  const delim = (first.match(/;/g) || []).length > (first.match(/,/g) || []).length ? ";" : ",";
  const rows = [];
  let row = [], cell = "", inQuotes = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (inQuotes) {
      if (c === '"') {
        if (text[i + 1] === '"') { cell += '"'; i++; } else inQuotes = false;
      } else cell += c;
    } else if (c === '"') inQuotes = true;
    else if (c === delim) { row.push(cell); cell = ""; }
    else if (c === "\n" || c === "\r") {
      if (c === "\r" && text[i + 1] === "\n") i++;
      row.push(cell); rows.push(row); row = []; cell = "";
    } else cell += c;
  }
  if (cell !== "" || row.length) { row.push(cell); rows.push(row); }
  return rows.map((r) => r.map((x) => x.trim())).filter((r) => r.some((x) => x !== ""));
}

const DOMAINE_ALIAS = {
  cloud: "Cloud", cyber: "Cyber", cybersecurity: "Cyber", "cybersécurité": "Cyber", cybersecurite: "Cyber",
  archi: "Archi", architecture: "Archi", web: "Web", "web et mobile": "Web",
  general: "General", "général": "General", generale: "General", "générale": "General",
};

function normaliserDomaine(valeur, disponibles) {
  const k = (valeur || "").trim().toLowerCase();
  const v = DOMAINE_ALIAS[k];
  if (v && disponibles.includes(v)) return v;
  return disponibles.find((d) => d.toLowerCase() === k) || null;
}

/**
 * Accepte "email,Domaine" (format du lab) ou "email,nom,domaine1|domaine2".
 * Regroupe par email (union des domaines). Ignore une ligne d'en-tête.
 */
function grouperImport(rows, disponibles) {
  if (rows.length && !rows[0][0].includes("@")) rows = rows.slice(1);
  const parEmail = new Map();
  const rejets = [];
  rows.forEach((r, i) => {
    const email = (r[0] || "").toLowerCase();
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) { rejets.push(`Ligne ${i + 1} : email invalide (${r[0] || "vide"})`); return; }
    const entree = parEmail.get(email) || { email, nom: "", domaines: [] };
    r.slice(1).forEach((cellule) => {
      cellule.split("|").map((t) => t.trim()).filter(Boolean).forEach((token) => {
        const d = normaliserDomaine(token, disponibles);
        if (d) { if (!entree.domaines.includes(d)) entree.domaines.push(d); }
        else if (!entree.nom) entree.nom = token;
        else rejets.push(`Ligne ${i + 1} : « ${token} » ignoré (domaine inconnu)`);
      });
    });
    parEmail.set(email, entree);
  });
  return { etudiants: [...parEmail.values()], rejets };
}

function toCsv(entetes, lignes) {
  const q = (v) => `"${String(v ?? "").replace(/"/g, '""')}"`;
  return "\uFEFF" + [entetes, ...lignes].map((l) => l.map(q).join(";")).join("\r\n");
}

function telechargerCsv(nom, contenu) {
  const url = URL.createObjectURL(new Blob([contenu], { type: "text/csv;charset=utf-8" }));
  const a = document.createElement("a");
  a.href = url; a.download = nom; a.click();
  URL.revokeObjectURL(url);
}

// ---------------------------------------------------------------------
// Tableau : recherche, filtres, tri par colonne, pagination
// ---------------------------------------------------------------------

class DataTable {
  /**
   * cfg.columns : [{ key, label, html(row), sort(row) (optionnel) }]
   * cfg.searchText(row) : texte indexé par la recherche
   * cfg.filters : [{ id, label, options: [{value,label}], test(row, value) }]
   * cfg.defaultSort : { key, dir: "asc" | "desc" }
   */
  constructor(containerId, cfg) {
    this.el = document.getElementById(containerId);
    this.cfg = { pageSize: 15, empty: "Aucun résultat.", filters: [], ...cfg };
    this.rows = [];
    this.search = "";
    this.filterValues = {};
    this.sortState = cfg.defaultSort || null;
    this.page = 1;
    this.buildToolbar();
  }

  buildToolbar() {
    const filtres = this.cfg.filters.map((f) => `
      <select data-filter="${f.id}" aria-label="${escapeHtml(f.label)}">
        <option value="">${escapeHtml(f.label)} : tous</option>
        ${f.options.map((o) => `<option value="${escapeHtml(o.value)}">${escapeHtml(o.label)}</option>`).join("")}
      </select>`).join("");
    this.el.innerHTML = `
      <div class="toolbar">
        <input type="search" data-search placeholder="Rechercher…" aria-label="Rechercher" />
        ${filtres}
        <span class="toolbar-count" data-count></span>
      </div>
      <div class="table-wrap" data-body></div>
      <div class="pager" data-pager></div>`;

    this.el.querySelector("[data-search]").addEventListener("input", (e) => {
      this.search = e.target.value.trim().toLowerCase(); this.page = 1; this.render();
    });
    this.el.querySelectorAll("[data-filter]").forEach((sel) =>
      sel.addEventListener("change", (e) => {
        this.filterValues[e.target.dataset.filter] = e.target.value; this.page = 1; this.render();
      }));
    this.el.addEventListener("click", (e) => {
      const th = e.target.closest("th[data-sort]");
      if (th) {
        const key = th.dataset.sort;
        const dir = this.sortState?.key === key && this.sortState.dir === "asc" ? "desc" : "asc";
        this.sortState = { key, dir }; this.render();
      }
      const pg = e.target.closest("[data-page]");
      if (pg && !pg.disabled) { this.page = Number(pg.dataset.page); this.render(); }
    });
  }

  setRows(rows) { this.rows = rows || []; this.page = 1; this.render(); }

  getFiltered() {
    let out = this.rows;
    if (this.search) out = out.filter((r) => (this.cfg.searchText?.(r) || "").toLowerCase().includes(this.search));
    for (const f of this.cfg.filters) {
      const v = this.filterValues[f.id];
      if (v) out = out.filter((r) => f.test(r, v));
    }
    if (this.sortState) {
      const col = this.cfg.columns.find((c) => c.key === this.sortState.key);
      if (col?.sort) {
        const sens = this.sortState.dir === "asc" ? 1 : -1;
        out = [...out].sort((a, b) => {
          const x = col.sort(a), y = col.sort(b);
          if (typeof x === "number" && typeof y === "number") return (x - y) * sens;
          return String(x ?? "").localeCompare(String(y ?? ""), "fr", { numeric: true }) * sens;
        });
      }
    }
    return out;
  }

  render() {
    const data = this.getFiltered();
    const { pageSize, columns } = this.cfg;
    const pages = Math.max(1, Math.ceil(data.length / pageSize));
    this.page = Math.min(this.page, pages);
    const visibles = data.slice((this.page - 1) * pageSize, this.page * pageSize);

    this.el.querySelector("[data-count]").textContent =
      `${data.length} résultat${data.length > 1 ? "s" : ""}`;

    const body = this.el.querySelector("[data-body]");
    if (!visibles.length) {
      body.innerHTML = `<div class="empty-state">${escapeHtml(this.cfg.empty)}</div>`;
    } else {
      const fleche = (c) => (this.sortState?.key === c.key ? (this.sortState.dir === "asc" ? " ▲" : " ▼") : "");
      body.innerHTML = `<table>
        <thead><tr>${columns.map((c) =>
          `<th ${c.sort ? `data-sort="${c.key}" class="sortable"` : ""}>${escapeHtml(c.label)}${c.sort ? fleche(c) : ""}</th>`).join("")}</tr></thead>
        <tbody>${visibles.map((r) => `<tr>${columns.map((c) => `<td>${c.html(r)}</td>`).join("")}</tr>`).join("")}</tbody>
      </table>`;
    }

    this.el.querySelector("[data-pager]").innerHTML = pages > 1 ? `
      <button class="btn-secondary" data-page="${this.page - 1}" ${this.page === 1 ? "disabled" : ""}>Précédent</button>
      <span>Page ${this.page} / ${pages}</span>
      <button class="btn-secondary" data-page="${this.page + 1}" ${this.page === pages ? "disabled" : ""}>Suivant</button>` : "";
  }
}
