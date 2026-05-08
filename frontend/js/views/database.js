import { state, showSpinner, hideSpinner, showToast } from '../app.js';
import { apiCall } from '../api.js';

// ---------- ÉTAT LOCAL ----------
let currentTab = 'items';
let tables = {};

// Données brutes chargées une fois
let itemsData = [];
let columnsData = [];
let invoicesData = [];
let concessionsData = [];

// Références aux instances Tabulator
const tabulatorInstances = {};

export async function initDatabaseView() {
  const root = document.getElementById('database-root');
  showSpinner();

  try {
    // Chargement parallèle des données
    const [items, columns, invoices, concessions] = await Promise.all([
      apiCall('GET', '/items'),
      apiCall('GET', '/colonnes'),
      apiCall('GET', '/factures'),
      apiCall('GET', '/concessions')
    ]);
    itemsData = items;
    columnsData = columns;
    invoicesData = invoices;
    concessionsData = concessions;

    // Construction de la vue
    root.innerHTML = buildLayout();

    // Initialiser le dashboard KPI
    updateKPIs();

    // Initialiser les onglets
    initTabs();

    // Charger le premier onglet
    await renderTab('items');

    // Événements sur les onglets
    document.querySelectorAll('.an-tab[data-tab]').forEach(tab => {
      tab.addEventListener('click', async (e) => {
        const tabId = e.currentTarget.dataset.tab;
        if (tabId === currentTab) return;
        setActiveTab(tabId);
        await renderTab(tabId);
      });
    });
  } catch (err) {
    console.error(err);
    root.innerHTML = '<div class="no-data"><div class="nd-icon">⚠️</div>Erreur de chargement</div>';
  } finally {
    hideSpinner();
  }
}

// ─── Layout principal ───
function buildLayout() {
  return /*html*/`
    <div class="an-header">
      <div class="an-header-left">
        <div class="an-eyebrow">DATA MANAGEMENT</div>
        <h1 class="an-title">Base de <span>données</span></h1>
        <p class="an-subtitle">Gérez les items, colonnes, factures et concessions</p>
      </div>
      <div class="live-badge">
        <div class="live-dot"></div>
        Synchronisée
      </div>
    </div>

    <!-- KPI Dashboard -->
    <div id="db-kpi-section"></div>

    <!-- Onglets -->
    <div class="an-tabs mb-3">
      <button class="an-tab active" data-tab="items">🏷️ Items</button>
      <button class="an-tab" data-tab="columns">📊 Colonnes</button>
      <button class="an-tab" data-tab="invoices">📄 Factures</button>
      <button class="an-tab" data-tab="concessions">🏢 Concessions</button>
    </div>

    <!-- Barre d'outils spécifique à chaque onglet -->
    <div id="tab-toolbar" class="mb-3"></div>

    <!-- Conteneur de la table -->
    <div id="tab-table-container" class="card-custom" style="padding: 0;"></div>
  `;
}

// ─── KPI Cards ───
function updateKPIs() {
  const kpiSection = document.getElementById('db-kpi-section');
  if (!kpiSection) return;
  kpiSection.innerHTML = `
    <div class="kpi-card kpi-accent-cyan">
      <div class="kpi-icon">🏷️</div>
      <div class="kpi-label">Total Items</div>
      <div class="kpi-value">${itemsData.length}</div>
    </div>
    <div class="kpi-card kpi-accent-blue">
      <div class="kpi-icon">📊</div>
      <div class="kpi-label">Colonnes</div>
      <div class="kpi-value">${columnsData.length}</div>
    </div>
    <div class="kpi-card kpi-accent-pink">
      <div class="kpi-icon">📄</div>
      <div class="kpi-label">Factures</div>
      <div class="kpi-value">${invoicesData.length}</div>
    </div>
    <div class="kpi-card kpi-accent-ok">
      <div class="kpi-icon">🏢</div>
      <div class="kpi-label">Concessions</div>
      <div class="kpi-value">${concessionsData.length}</div>
    </div>
  `;
}

// ─── Gestion des onglets ───
function setActiveTab(tabId) {
  currentTab = tabId;
  document.querySelectorAll('.an-tab').forEach(t => t.classList.remove('active'));
  document.querySelector(`.an-tab[data-tab="${tabId}"]`).classList.add('active');
}

function initTabs() {
  setActiveTab('items');
}

// ─── Rendu spécifique à chaque onglet ───
async function renderTab(tabId) {
  const toolbar = document.getElementById('tab-toolbar');
  const tableContainer = document.getElementById('tab-table-container');

  // Détruire l'instance Tabulator précédente si elle existe
  if (tabulatorInstances[tabId]) {
    tabulatorInstances[tabId].destroy();
    delete tabulatorInstances[tabId];
  }

  // Vider le conteneur
  tableContainer.innerHTML = '';

  switch (tabId) {
    case 'items':
      toolbar.innerHTML = buildItemsToolbar();
      await buildItemsTable(tableContainer);
      break;
    case 'columns':
      toolbar.innerHTML = buildColumnsToolbar();
      await buildColumnsTable(tableContainer);
      break;
    case 'invoices':
      toolbar.innerHTML = '';
      await buildInvoicesTable(tableContainer);
      break;
    case 'concessions':
      toolbar.innerHTML = buildConcessionsToolbar();
      await buildConcessionsTable(tableContainer);
      break;
  }
}

// ─── Toolbars (boutons d'action) ───
function buildItemsToolbar() {
  return `
    <div class="d-flex justify-content-between align-items-center">
      <button class="btn btn-sm btn-analyse" id="add-item-btn"><i class="fas fa-plus me-1"></i> Ajouter</button>
      <div class="d-flex gap-2">
        <input type="text" id="item-search" class="table-search" placeholder="🔍 Rechercher...">
        <button class="btn btn-sm btn-outline-danger" id="delete-selected-items" disabled>
          <i class="fas fa-trash me-1"></i> Supprimer sélection
        </button>
      </div>
    </div>
  `;
}

function buildColumnsToolbar() {
  return `
    <div class="d-flex justify-content-between align-items-center">
      <button class="btn btn-sm btn-analyse" id="add-column-btn"><i class="fas fa-plus me-1"></i> Ajouter</button>
      <button class="btn btn-sm btn-outline-danger" id="delete-selected-columns" disabled>
        <i class="fas fa-trash me-1"></i> Supprimer sélection
      </button>
    </div>
  `;
}

function buildConcessionsToolbar() {
  return `
    <div class="d-flex justify-content-between align-items-center">
      <button class="btn btn-sm btn-analyse" id="add-concession-btn"><i class="fas fa-plus me-1"></i> Ajouter</button>
    </div>
  `;
}

// ─── Tables Tabulator ───
async function buildItemsTable(container) {
  const items = itemsData.map(it => ({
    id: it.id_item,
    libelle: it.libelle_canonique,
    concession: concessionsData.find(c => c.id_concession === it.id_concession)?.nom || '—',
    usage: it.usage_count   // ← directement depuis l'API
}));



  const table = new Tabulator(container, {
    data: items,
    layout: 'fitColumns',
    height: 400,
    columns: [
      { title: 'ID', field: 'id', width: 80, frozen: true },
      { title: 'Libellé', field: 'libelle', editor: 'input', headerFilter: true },
      { title: 'Concession', field: 'concession', editor: 'select', editorParams: { values: concessionsData.reduce((acc, c) => ({ ...acc, [c.nom]: c.id_concession }), {}) } },
      {
        title: 'Utilisé dans',
        field: 'usage',
        hozAlign: 'center',
        formatter: function(cell, formatterParams, onRendered) {
          const val = cell.getValue();
          return val > 0 ? `<span class="status-badge completed">${val} facture(s)</span>` : '<span class="text-muted">—</span>';
        }
      }
    ],
    selectable: true,
    rowFormatter: function(row) {
      const data = row.getData();
      if (data.usage > 0) {
        row.getElement().style.opacity = '0.7';
      }
    },
    footerElement: `<div style='padding:8px; text-align:right; font-weight:bold;'>Total items : <span>${items.length}</span></div>`
  });

  tabulatorInstances.items = table;

  // Gérer le bouton "Supprimer sélection"
  const deleteBtn = document.getElementById('delete-selected-items');
  table.on('rowSelectionChanged', function(data, rows) {
    const hasSelected = table.getSelectedRows().length > 0;
    deleteBtn.disabled = !hasSelected;
  });

  deleteBtn.addEventListener('click', async () => {
    const selectedRows = table.getSelectedRows();
    const ids = selectedRows.map(row => row.getData().id);
    // Vérifier si certains sont utilisés
    const usedIds = ids.filter(id => items.find(it => it.id === id)?.usage > 0);
    if (usedIds.length) {
      showToast(`${usedIds.length} item(s) sont utilisés et ne peuvent être supprimés`, 'warning');
      return;
    }
    if (!confirm(`Supprimer ${ids.length} item(s) ?`)) return;
    showSpinner();
    try {
      await apiCall('DELETE', '/items', ids);
      showToast('Items supprimés', 'success');
      await initDatabaseView(); // recharger
    } catch (err) {
      showToast('Erreur suppression', 'danger');
    } finally {
      hideSpinner();
    }
  });

  // Ajouter un nouvel item
  document.getElementById('add-item-btn')?.addEventListener('click', async () => {
    const libelle = prompt('Libellé du nouvel item :');
    if (!libelle) return;
    const concessionId = prompt('ID de la concession (ou laisser vide) :');
    showSpinner();
    try {
      await apiCall('POST', '/items', null, { libelle_canonique: libelle, id_concession: concessionId || null });
      showToast('Item créé', 'success');
      await initDatabaseView();
    } catch (err) {
      showToast('Erreur création', 'danger');
    } finally {
      hideSpinner();
    }
  });

  // Recherche
  document.getElementById('item-search')?.addEventListener('input', (e) => {
    table.setFilter('libelle', 'like', e.target.value);
  });
}

async function buildColumnsTable(container) {
  const cols = columnsData.map(c => ({
    id: c.id_colonne,
    libelle: c.libelle_canonique,
    concession: concessionsData.find(co => co.id_concession === c.id_concession)?.nom || '—',
    usage: c.usage_count   // ← directement depuis l'API
}));

  const table = new Tabulator(container, {
    data: cols,
    layout: 'fitColumns',
    height: 400,
    columns: [
      { title: 'ID', field: 'id', width: 80 },
      { title: 'Libellé', field: 'libelle', editor: 'input', headerFilter: true },
      { title: 'Concession', field: 'concession', editor: 'select', editorParams: { values: concessionsData.reduce((acc, c) => ({ ...acc, [c.nom]: c.id_concession }), {}) } },
      {
        title: 'Utilisation',
        field: 'usage',
        formatter: 'tickCross',
        headerFilter: 'tickCross'
      }
    ],
    selectable: true,
    footerElement: `<div style='padding:8px; text-align:right; font-weight:bold;'>Total colonnes : <span>${cols.length}</span></div>`
  });

  tabulatorInstances.columns = table;

  const deleteBtn = document.getElementById('delete-selected-columns');
  table.on('rowSelectionChanged', () => {
    deleteBtn.disabled = table.getSelectedRows().length === 0;
  });

  deleteBtn.addEventListener('click', async () => {
    const selectedRows = table.getSelectedRows();
    const ids = selectedRows.map(r => r.getData().id);
    const usedIds = ids.filter(id => cols.find(c => c.id === id)?.usage > 0);
    if (usedIds.length) {
      showToast(`${usedIds.length} colonne(s) utilisée(s), suppression interdite`, 'warning');
      return;
    }
    if (!confirm('Confirmer la suppression ?')) return;
    showSpinner();
    try {
      await apiCall('DELETE', '/colonnes', ids);
      showToast('Colonnes supprimées', 'success');
      await initDatabaseView();
    } catch (err) {
      showToast('Erreur suppression', 'danger');
    } finally {
      hideSpinner();
    }
  });

  document.getElementById('add-column-btn')?.addEventListener('click', async () => {
    const libelle = prompt('Libellé de la nouvelle colonne :');
    if (!libelle) return;
    const concessionId = prompt('ID concession (ou vide) :');
    showSpinner();
    try {
      await apiCall('POST', '/colonnes', null, { libelle_canonique: libelle, id_concession: concessionId || null });
      showToast('Colonne créée', 'success');
      await initDatabaseView();
    } catch (err) {
      showToast('Erreur création', 'danger');
    } finally {
      hideSpinner();
    }
  });
}

async function buildInvoicesTable(container) {
  const invoices = invoicesData.map(f => ({
    id: f.id_facture,
    date: f.date_facture ? f.date_facture.split('T')[0] : '—',
    concession: concessionsData.find(c => c.id_concession === f.id_concession)?.nom || '—',
    fichier: f.fichier_source,
    montant: f.total_montant?.toFixed(2) + ' ' + (f.devise || '€')
  }));

  const table = new Tabulator(container, {
    data: invoices,
    layout: 'fitColumns',
    height: 400,
    columns: [
      { title: 'ID', field: 'id', width: 80 },
      { title: 'Date', field: 'date', sorter: 'date' },
      { title: 'Concession', field: 'concession' },
      { title: 'Fichier', field: 'fichier' },
      { title: 'Montant', field: 'montant', hozAlign: 'right' }
    ],
    footerElement: `<div style='padding:8px; text-align:right; font-weight:bold;'>Total factures : <span>${invoices.length}</span></div>`
  });

  tabulatorInstances.invoices = table;
}

async function buildConcessionsTable(container) {
  const concessions = concessionsData.map(c => ({
    id: c.id_concession,
    nom: c.nom,
    date: c.date_creation ? c.date_creation.split('T')[0] : '—'
  }));

  const table = new Tabulator(container, {
    data: concessions,
    layout: 'fitColumns',
    height: 400,
    columns: [
      { title: 'ID', field: 'id', width: 80 },
      { title: 'Nom', field: 'nom', editor: 'input' },
      { title: 'Date création', field: 'date' }
    ],
    footerElement: `<div style='padding:8px; text-align:right; font-weight:bold;'>Total concessions : <span>${concessions.length}</span></div>`
  });

  tabulatorInstances.concessions = table;

  document.getElementById('add-concession-btn')?.addEventListener('click', async () => {
    const nom = prompt('Nom de la nouvelle concession :');
    if (!nom) return;
    showSpinner();
    try {
      await apiCall('POST', '/concessions', null, { nom });
      showToast('Concession créée', 'success');
      await initDatabaseView();
    } catch (err) {
      showToast('Erreur création', 'danger');
    } finally {
      hideSpinner();
    }
  });
}