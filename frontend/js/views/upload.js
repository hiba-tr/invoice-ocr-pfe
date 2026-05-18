import { state, showSpinner, hideSpinner, showToast } from '../app.js';
import { API_BASE, apiCall } from '../api.js';

export function initUploadView() {
  const fileInput = document.getElementById('file-input');
  const browseBtn = document.getElementById('browse-btn');
  const uploadArea = document.getElementById('upload-area');
  const extractBtn = document.getElementById('extract-btn');

  browseBtn?.addEventListener('click', (e) => {
    e.stopPropagation();
    fileInput.click();
  });

  uploadArea?.addEventListener('click', (e) => {
    if (!e.target.closest('#browse-btn')) {
      fileInput.click();
    }
  });
  uploadArea?.addEventListener('dragover', (e) => { e.preventDefault(); uploadArea.classList.add('dragover'); });
uploadArea?.addEventListener('dragleave', () => uploadArea.classList.remove('dragover'));
 // Remplace les gestionnaires de drop et change par :
uploadArea?.addEventListener('drop', (e) => {
  e.preventDefault();
  uploadArea.classList.remove('dragover');
  if (e.dataTransfer.files.length) {
    Array.from(e.dataTransfer.files).forEach(f => handleFileSelect(f));
  }
});
fileInput?.addEventListener('change', (e) => {
  if (e.target.files.length) {
    Array.from(e.target.files).forEach(f => handleFileSelect(f));
  }
});

  // ---------- GESTION DE LA FILE D'ATTENTE ----------
let selectedFiles = [];

function updateFileQueue() {
  const queueEl = document.getElementById('file-queue');
  const queueList = document.getElementById('queue-list');
  if (!queueEl || !queueList) return;
  if (selectedFiles.length === 0) {
    queueEl.style.display = 'none';
    return;
  }
  queueEl.style.display = 'block';
  queueList.innerHTML = selectedFiles
    .map(
      (f, i) => `
      <div class="queue-item">
        <i class="fas fa-file" style="color: var(--accent);"></i>
        <span class="file-name">${f.name}</span>
        <span style="font-size:12px; color: var(--text-muted);">${(f.size / 1024).toFixed(1)} KB</span>
        <button class="btn btn-sm remove-file" data-index="${i}">
          <i class="fas fa-times"></i>
        </button>
      </div>`
    )
    .join('');
  // Événements de suppression
  queueList.querySelectorAll('.remove-file').forEach(btn =>
    btn.addEventListener('click', (e) => {
      const idx = parseInt(btn.dataset.index);
      selectedFiles.splice(idx, 1);
      updateFileQueue();
      extractBtn.disabled = selectedFiles.length === 0;
    })
  );
}

function handleFileSelect(file) {
  // Ajouter chaque nouveau fichier à la liste
  selectedFiles.push(file);
  updateFileQueue();
  extractBtn.disabled = selectedFiles.length === 0;
}
extractBtn?.addEventListener('click', async () => {
  if (selectedFiles.length === 0) return;

  const progressContainer = document.getElementById('progress-container');
  const progressBar = document.getElementById('progress-bar');
  const progressText = document.getElementById('progress-text');

  // Afficher la barre de progression
  if (progressContainer) {
    progressContainer.style.display = 'block';
    progressBar.style.width = '0%';
    progressText.textContent = '0%';
  }

  showSpinner();
  try {
    for (let i = 0; i < selectedFiles.length; i++) {
      const file = selectedFiles[i];

      // Mise à jour de la progression
      const progress = Math.round(((i + 1) / selectedFiles.length) * 100);
      if (progressBar) progressBar.style.width = `${progress}%`;
      if (progressText) progressText.textContent = `${progress}%`;

      const formData = new FormData();
      formData.append('file', file);
      const resp = await axios.post(API_BASE + '/upload', formData);
      // Garde le dernier résultat pour l'affichage
      state.extractionResult = resp.data;
      state.suggestions = [];
      state.selectedInvoiceIndex = 0;
      state.editedTableData = [];
      state.tableInstance = null;
    }

    // Enregistre le premier fichier pour l'affichage du nom
    state.uploadedFile = selectedFiles[0];

    // Affiche les résultats
    renderExtractionResults();
    showToast('Extraction réussie', 'success');

    // Nettoie la file d'attente
    selectedFiles = [];
    updateFileQueue();
    extractBtn.disabled = true;
  } catch (err) {
    showToast('Échec de l’extraction', 'danger');
  } finally {
    hideSpinner();
    // Masque la progression après un court délai
    if (progressContainer) {
      setTimeout(() => { progressContainer.style.display = 'none'; }, 1000);
    }
  }
});

function renderExtractionResults() {
  const container = document.getElementById('extraction-results');
  container.style.display = 'block';
  const data = state.extractionResult;

  const sections = data.sections || [];
  const allItems = sections.flatMap(s => s.items || []);
  const identity = data.identity || {};

  const metadata = {
    company: identity.company,
    date: identity.period,
    currency: identity.currency,
    concession: identity.concession,
    first_column_name: data.columns?.headers?.[0] || 'Description'
  };

  const nbItems = allItems.length;
  const totalAmount = allItems.reduce((sum, it) => {
    const vals = Object.values(it.amounts || {});
    const numericVals = vals.map(v => (v && v.value) || 0);
    return sum + numericVals.reduce((a, b) => a + b, 0);
  }, 0).toFixed(2);

  let html = '';

  // Header des résultats
  html += `
    <div class="an-header mb-3">
      <div class="an-header-left">
        <div class="an-eyebrow">Résultat</div>
        <h2 class="an-title" style="font-size:22px;">Extraction <span>terminée</span></h2>
      </div>
      <div class="live-badge"><div class="live-dot"></div>OCR Validé</div>
    </div>
  `;

  // KPI cards style Analyses
   // KPI cards redimensionnées (3 colonnes)
  html += `
    <div class="row g-3 mb-4">
      <div class="col-md-4">
        <div class="kpi-card kpi-accent-cyan">
          <div class="kpi-icon">📄</div>
          <div class="kpi-label">Fichier traité</div>
          <div class="kpi-value" style="font-size:18px;">${state.uploadedFile?.name || '—'}</div>
        </div>
      </div>
      <div class="col-md-4">
        <div class="kpi-card kpi-accent-ok">
          <div class="kpi-icon">✅</div>
          <div class="kpi-label">Articles extraits</div>
          <div class="kpi-value">${nbItems}</div>
        </div>
      </div>
      <div class="col-md-4">
        <div class="kpi-card kpi-accent-blue">
          <div class="kpi-icon">💰</div>
          <div class="kpi-label">Montant total estimé</div>
          <div class="kpi-value kpi-cyan">${totalAmount} €</div>
        </div>
      </div>
    </div>
  `;

  // Métadonnées
    // Métadonnées (sans client, sans objet)
  html += `
    <div class="card-custom mb-4">
      <h5 class="fw-bold mb-3" style="font-family:var(--font-display);"><i class="fas fa-info-circle me-2" style="color:var(--accent);"></i>Métadonnées</h5>
      <div class="row g-3">
        <div class="col-md-6"><label class="form-label" style="font-family:var(--font-mono); font-size:10px; text-transform:uppercase;">Concession</label><div id="concession-field"></div></div>
        <div class="col-md-6"><label class="form-label" style="font-family:var(--font-mono); font-size:10px; text-transform:uppercase;">Date facture</label><input type="date" class="an-input form-control" id="meta-date" value="${metadata.date || ''}"></div>
        <div class="col-md-6"><label class="form-label" style="font-family:var(--font-mono); font-size:10px; text-transform:uppercase;">Devise</label><input class="an-input form-control" id="meta-currency" value="${metadata.currency || 'TND'}"></div>
        <div class="col-md-6"><label class="form-label" style="font-family:var(--font-mono); font-size:10px; text-transform:uppercase;">Fournisseur</label><input class="an-input form-control" id="meta-company" value="${metadata.company || ''}"></div>
      </div>
    </div>
  `;

  // Table des articles
  html += `
    <div class="card-custom">
      <div class="d-flex justify-content-between align-items-center mb-3">
        <h5 class="fw-bold mb-0" style="font-family:var(--font-display);">Articles extraits</h5>
        <div>
          <button class="btn btn-sm btn-outline-primary me-2" id="add-column-btn"><i class="fas fa-plus"></i> Colonne</button>
          <button class="btn btn-sm btn-outline-primary" id="suggest-btn"><i class="fas fa-lightbulb"></i> Vérifier correspondances</button>
        </div>
      </div>
      <div id="tables-container"></div>
    </div>
  `;
  html += `<div id="suggestions-area" class="mt-3"></div>`;
  html += `
    <div class="mt-4 d-flex gap-3">
      <button id="save-btn" class="btn-analyse"><i class="fas fa-save me-2"></i>Enregistrer</button>
      <div class="form-check mt-2"><input class="form-check-input" type="checkbox" id="force-overwrite"><label class="form-check-label">Écraser si existe</label></div>
    </div>
  `;

  container.innerHTML = html;

  // Initialisation des champs et de la table (inchangé)
  initTablesFromSections(sections, data.columns);

  setTimeout(() => initConcessionField(metadata.concession), 10);
  document.getElementById('add-column-btn')?.addEventListener('click', addNewColumn);
  document.getElementById('suggest-btn')?.addEventListener('click', autoApplySuggestions);
  document.getElementById('save-btn')?.addEventListener('click', saveFacture);
}

async function initConcessionField(defaultName) {
  if (state.concessionsList.length === 0) {
    try { state.concessionsList = await apiCall('GET', '/concessions'); } catch (e) { state.concessionsList = []; }
  }
  const container = document.getElementById('concession-field');
  if (!container) return;

  if (defaultName) {
    try {
      const match = await apiCall('GET', '/match-concession', null, { nom_extrait: defaultName });
      if (match.matched) {
        state.currentConcessionId = match.concession_id;
        state.currentConcessionNom = match.concession_nom;
        container.innerHTML = `<div class="alert alert-success py-2"><i class="fas fa-check-circle me-1"></i> Concession reconnue : <strong>${match.concession_nom}</strong></div>`;
        // ✅ AJOUT : déclenchement automatique des suggestions après match
        autoApplySuggestions();
        return;
      }
    } catch (e) {}
  }

  let options = state.concessionsList.map(c => `<option value="${c.id_concession}">${c.nom}</option>`).join('');
  container.innerHTML = `
    <div class="input-group">
      <select class="form-select" id="concession-select"><option value="">-- Sélectionner --</option>${options}</select>
      <input type="text" class="form-control" id="new-concession-name" placeholder="Ou créer nouvelle">
      <button class="btn btn-outline-secondary" type="button" id="create-concession-btn">Créer</button>
    </div>
    <small class="text-warning">Concession non reconnue, veuillez choisir ou créer.</small>
  `;

  document.getElementById('create-concession-btn')?.addEventListener('click', async () => {
    const newName = document.getElementById('new-concession-name')?.value.trim();
    if (!newName) return;
    showSpinner();
    try {
      const newC = await apiCall('POST', '/concessions', null, { nom: newName });
      state.concessionsList.push(newC);
      state.currentConcessionId = newC.id_concession;
      state.currentConcessionNom = newC.nom;
      container.innerHTML = `<div class="alert alert-success py-2">Concession créée : <strong>${newC.nom}</strong></div>`;
      // ✅ AJOUT : déclenchement automatique après création d'une concession
      autoApplySuggestions();
    } catch (e) { showToast('Erreur création concession', 'danger'); }
    finally { hideSpinner(); }
  });

  document.getElementById('concession-select')?.addEventListener('change', (e) => {
    if (e.target.value) {
      state.currentConcessionId = parseInt(e.target.value);
      const selected = state.concessionsList.find(c => c.id_concession === state.currentConcessionId);
      state.currentConcessionNom = selected?.nom || '';
      // ✅ AJOUT : déclenchement automatique après sélection manuelle
      autoApplySuggestions();
    }
  });
}

// ✅ AJOUT : Nouvelle fonction qui applique automatiquement les suggestions
async function autoApplySuggestions() {
  if (!state.currentConcessionId || !state.tableInstance) return;

  const data = state.tableInstance.getData();
  let updatedCount = 0;

  for (let i = 0; i < data.length; i++) {
    const desc = data[i].description;
    if (!desc) continue;

    try {
      const resp = await apiCall('GET', '/suggest', null, {
        description: desc,
        id_concession: state.currentConcessionId
      });
      if (resp.item_id) {
        // Appliquer immédiatement la suggestion sur la ligne correspondante
        state.tableInstance.updateData([{ id: data[i].id, description: resp.libelle_canonique }]);
        updatedCount++;
      }
    } catch (e) {
      // ignorer les échecs individuels
    }
  }

  if (updatedCount > 0) {
    showToast(`${updatedCount} article(s) harmonisé(s) avec la base`, 'info');
  }
}
function initTablesFromSections(sections, globalSchema) {
  const tablesContainer = document.getElementById('tables-container');
  if (!tablesContainer) return;
  tablesContainer.innerHTML = '';

  state.secondaryTables = [];   // pour stocker les instances Tabulator secondaires

  sections.forEach((section, idx) => {
    const sectionSchema = section.columns || globalSchema;
    if (!sectionSchema || !sectionSchema.headers || sectionSchema.headers.length === 0) return;

    const containerId = `items-table-${idx}`;
    const sectionDiv = document.createElement('div');
    sectionDiv.className = 'card-custom mb-3';
    sectionDiv.innerHTML = `
      <h5 class="fw-bold mb-3" style="font-family:var(--font-display);">${section.name || 'Tableau ' + (idx+1)}</h5>
      <div id="${containerId}" style="min-height:200px;"></div>
    `;
    tablesContainer.appendChild(sectionDiv);

    initItemsTable(section.items || [], sectionSchema.headers[0] || 'Description', containerId, sectionSchema);
  });
}
function recalculerTotauxTable(table, containerId) {
  if (!table) return;
  const data = table.getData();
  const columns = table.getColumns();
  const montantFields = columns.map(col => col.getField()).filter(f => f !== 'description' && f !== '__total_ligne');
  let totalGeneral = 0;
  data.forEach(row => {
    let totalLigne = 0;
    montantFields.forEach(field => {
      const val = row[field];
      if (val !== undefined && val !== null && val !== '') {
        let strVal = String(val).replace(/[^\d.,\-()]/g, '');
        if (strVal.startsWith('(') && strVal.endsWith(')')) strVal = '-' + strVal.slice(1, -1);
        const num = parseFloat(strVal.replace(',', '.'));
        if (!isNaN(num)) totalLigne += num;
      }
    });
    row['__total_ligne'] = totalLigne;
    totalGeneral += totalLigne;
  });
  const footerSpan = document.getElementById(`total-general-footer-${containerId}`);
  if (footerSpan) footerSpan.textContent = totalGeneral.toFixed(2) + ' €';
  if (containerId === 'items-table' || containerId === 'items-table-0') {
    state.totalGeneral = totalGeneral;
  }
  table.blockRedraw();
  try {
    data.forEach((row, idx) => {
      const rowComp = table.getRows()[idx];
      if (rowComp) rowComp.update({ __total_ligne: row.__total_ligne });
    });
  } finally {
    table.restoreRedraw();
  }
}
// ---- Le reste des fonctions (table, calculs, colonnes, etc.) reste inchangé ----
let isCalculating = false;
let tableInstance = null;
function initItemsTable(items, firstColName, containerId = 'items-table', schemaOverride = null) {
  const schema = schemaOverride || state.extractionResult.columns;
  if (!schema || !schema.headers) {
    console.warn('Schéma de colonnes introuvable');
    return;
  }

  const headers = schema.headers;
  const semantics = schema.semantics;

  // 1. Construire des champs UNIQUES (même sémantiques)
  const fieldCount = {};
  const uniqueFields = semantics.map((sem, i) => {
    let field = sem || `col_${i}`;
    if (fieldCount[field] !== undefined) {
      fieldCount[field]++;
      field = `${field}_${fieldCount[field]}`;
    } else {
      fieldCount[field] = 1;
    }
    return field;
  });

  // 2. Définitions des colonnes Tabulator
  const colDefs = headers.map((header, index) => {
    const field = uniqueFields[index];
    const isDescription = field === 'description' || field === 'designation' || field === 'libelle' || field === 'article' || field === 'item';
    return {
      title: header,
      field: field,
      editor: 'input',
      width: isDescription ? 250 : undefined,
      frozen: isDescription,
      formatter: function(cell) {
        const val = cell.getValue();
        if (val && typeof val === 'object' && val.raw !== undefined) {
          return val.raw;
        }
        return val !== undefined && val !== null ? val : '';
      }
    };
  });

  // 3. Colonne Total
  colDefs.push({
    title: 'Total',
    field: '__total_ligne',
    formatter: function(cell) {
      const val = cell.getValue();
      return val !== undefined ? val.toFixed(2) + ' €' : '';
    },
    hozAlign: 'right',
    width: 120,
    editor: false
  });

  // 4. Transformer les items en données Tabulator
  const tableData = items.map(it => {
    const row = { __total_ligne: 0 };

    // Trouver le champ de description (le premier champ qui correspond à une sémantique de description)
    const descField = uniqueFields.find((f, i) =>
      semantics[i] === 'description' || semantics[i] === 'designation' || semantics[i] === 'libelle' || semantics[i] === 'article' || semantics[i] === 'item'
    ) || uniqueFields[0];   // fallback : première colonne
    if (descField) {
      row[descField] = it.description;
    }

    // Placer les autres colonnes depuis it.amounts
    if (it.amounts) {
      Object.entries(it.amounts).forEach(([sem, val]) => {
        // Retrouver l'index de la sémantique dans le tableau d'origine
        const idx = semantics.indexOf(sem);
        if (idx !== -1) {
          const field = uniqueFields[idx];
          if (field !== descField) {
            row[field] = val;
          }
        } else {
          // fallback (ne devrait pas arriver)
          if (sem !== descField) {
            row[sem] = val;
          }
        }
      });
    }

    return row;
  });

  state.editedTableData = tableData;
  state.tableColumns = colDefs;

  // 5. Créer la table Tabulator
  const tableEl = document.getElementById(containerId);
  if (!tableEl) return;

  if (Tabulator.findTable(`#${containerId}`)) {
    Tabulator.findTable(`#${containerId}`).destroy();
  }

  const newTable = new Tabulator(`#${containerId}`, {
    data: tableData,
    columns: colDefs,
    layout: 'fitColumns',
    height: '400px',
    editable: true,
    movableColumns: true,
    headerMenu: [
      { label: "Renommer", action: (e, column) => renameColumn(column) },
      { label: "Supprimer", action: (e, column) => deleteColumn(column) }
    ],
    footerElement: `<div style='padding:8px; text-align:right; font-weight:bold;'>Total général : <span id='total-general-footer-${containerId}'>0.00 €</span></div>`
  });

  // Stocker la table principale
  if (containerId === 'items-table' || containerId === 'items-table-0') {
    state.tableInstance = newTable;
  } else {
    state.secondaryTables.push(newTable);
  }

  // Écouteurs avec la nouvelle fonction de calcul
  newTable.on('dataLoaded', () => recalculerTotauxTable(newTable, containerId));
  newTable.on('cellEdited', () => { recalculerTotauxTable(newTable, containerId); });
  setTimeout(() => recalculerTotauxTable(newTable, containerId), 50);
}
  function recalculerTotaux() {
  if (!state.tableInstance) return;
  const data = state.tableInstance.getData();
  const columns = state.tableInstance.getColumns();
  const montantFields = columns.map(col => col.getField()).filter(f => f !== 'description' && f !== '__total_ligne');
  let totalGeneral = 0;
  data.forEach(row => {
    let totalLigne = 0;
    montantFields.forEach(field => {
      const val = row[field];
      if (val !== undefined && val !== null && val !== '') {
        let strVal = String(val).replace(/[^\d.,\-()]/g, '');
        if (strVal.startsWith('(') && strVal.endsWith(')')) strVal = '-' + strVal.slice(1, -1);
        const num = parseFloat(strVal.replace(',', '.'));
        if (!isNaN(num)) totalLigne += num;
      }
    });
    row['__total_ligne'] = totalLigne;
    totalGeneral += totalLigne;
  });
  state.totalGeneral = totalGeneral;
  state.tableInstance.blockRedraw();
  try {
    data.forEach((row, idx) => {
      const rowComp = state.tableInstance.getRows()[idx];
      if (rowComp) rowComp.update({ __total_ligne: row.__total_ligne });
    });
  } finally {
    state.tableInstance.restoreRedraw();
  }
  mettreAJourFooter();
}

function mettreAJourFooter() {
  const footerSpan = document.getElementById('total-general-footer');
  if (footerSpan) footerSpan.textContent = (state.totalGeneral || 0).toFixed(2) + ' €';
}

function addNewColumn() {
  const colName = prompt('Nom de la nouvelle colonne :');
  if (!colName) return;
  if (state.tableColumns.some(c => c.field === colName)) { alert('Cette colonne existe déjà'); return; }
  const totalIndex = state.tableColumns.length - 1;
  state.tableColumns.splice(totalIndex, 0, { title: colName, field: colName, editor: 'input' });
  state.editedTableData.forEach(row => row[colName] = '');
  state.tableInstance.setColumns(state.tableColumns);
  state.tableInstance.setData(state.editedTableData);
  recalculerTotaux(); mettreAJourFooter();
}

function renameColumn(column) {
  const newName = prompt('Nouveau nom :', column.getField());
  if (!newName || newName === column.getField()) return;
  const field = column.getField();
  if (field === '__total_ligne') { alert('Impossible de renommer la colonne Total.'); return; }
  state.editedTableData.forEach(row => { if (row.hasOwnProperty(field)) { row[newName] = row[field]; delete row[field]; } });
  const colDef = state.tableColumns.find(c => c.field === field);
  if (colDef) colDef.field = newName;
  state.tableInstance.setColumns(state.tableColumns);
  state.tableInstance.setData(state.editedTableData);
  recalculerTotaux(); mettreAJourFooter();
}

function deleteColumn(column) {
  const field = column.getField();
  if (field === '__total_ligne') { alert('Impossible de supprimer la colonne Total.'); return; }
  if (!confirm(`Supprimer la colonne "${field}" ?`)) return;
  state.editedTableData.forEach(row => delete row[field]);
  state.tableColumns = state.tableColumns.filter(c => c.field !== field);
  state.tableInstance.setColumns(state.tableColumns);
  state.tableInstance.setData(state.editedTableData);
  recalculerTotaux(); mettreAJourFooter();
}

async function fetchSuggestions() {
  if (!state.currentConcessionId) { showToast('Veuillez d\'abord définir une concession', 'warning'); return; }
  showSpinner();
  try {
    const data = state.tableInstance.getData();
    const suggestions = [];
    for (let i = 0; i < data.length; i++) {
      const desc = data[i].description;
      if (!desc) continue;
      try {
        const resp = await apiCall('GET', '/suggest', null, { description: desc, id_concession: state.currentConcessionId });
        if (resp.item_id) suggestions.push({ index: i, description: desc, suggestion: resp.libelle_canonique, item_id: resp.item_id, confiance: resp.confiance });
      } catch (e) {}
    }
    state.suggestions = suggestions;
    renderSuggestions();
    showToast(`${suggestions.length} correspondance(s) trouvée(s)`, 'info');
  } finally { hideSpinner(); }
}

function renderSuggestions() {
  const area = document.getElementById('suggestions-area');
  if (!state.suggestions.length) { area.innerHTML = ''; return; }
  let html = `<h5>Correspondances trouvées</h5><div class="list-group">`;
  state.suggestions.forEach((s, idx) => {
    html += `<div class="list-group-item d-flex justify-content-between align-items-center">
      <span><strong>${s.description}</strong> → ${s.suggestion} <span class="badge bg-info">${Math.round(s.confiance*100)}%</span></span>
      <button class="btn btn-sm btn-outline-primary apply-suggestion" data-index="${idx}">Appliquer</button>
    </div>`;
  });
  html += `</div>`;
  area.innerHTML = html;
  document.querySelectorAll('.apply-suggestion').forEach(btn => {
    btn.addEventListener('click', (e) => {
      const idx = e.target.dataset.index;
      const sugg = state.suggestions[idx];
      state.tableInstance.updateData([{ id: sugg.index, description: sugg.suggestion }]);
      state.suggestions.splice(idx, 1);
      renderSuggestions();
    });
  });
}

async function saveFacture() {
  const date = document.getElementById('meta-date')?.value;
  const devise = document.getElementById('meta-currency')?.value || 'TND';
  const company = document.getElementById('meta-company')?.value;
  const force = document.getElementById('force-overwrite')?.checked || false;

  if (!state.currentConcessionId) { showToast('Concession non définie', 'danger'); return; }

  const facturePayload = {
    fichier_source: state.uploadedFile?.name || '',
    date_facture: date || null,
    devise,
    id_concession: state.currentConcessionId,
    nom_concession: state.currentConcessionNom,
    total_montant: state.totalGeneral || 0
  };

  const itemsData = state.tableInstance.getData().map(row => {
    const { description, __total_ligne, ...valeurs } = row;
    const cleanedValeurs = {};
    Object.entries(valeurs).forEach(([k, v]) => {
      if (v === undefined || v === null || v === '') return;
      cleanedValeurs[k] = String(v);
    });
    return { description, valeurs: cleanedValeurs };
  });

  const payload = { facture: facturePayload, items_data: itemsData };
  showSpinner();
  try {
    await apiCall('POST', '/facture', payload, { force });
    showToast('Facture enregistrée avec succès', 'success');
    state.extractionResult = null;
    state.uploadedFile = null;
    document.querySelector('#sidebar-nav [data-view="history"]').click();
  } catch (e) { showToast('Erreur lors de l\'enregistrement', 'danger'); }
  finally { hideSpinner(); }
}}