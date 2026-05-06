import { state, showSpinner, hideSpinner, showToast } from '../app.js';
import { apiCall } from '../api.js';

let manualConcessionId = null;
let manualConcessionNom = '';
let manualTableInstance = null;
let manualTableColumns = [];
let manualEditedData = [];
let manualIsCalculating = false;
let manualTotalGeneral = 0;
let manualExistingItems = [];

let pendingDescriptions = [];
let availableColumnNames = [];

export function initManualView() {
  const selectEl = document.getElementById('manual-concession-select');
  const newNameInput = document.getElementById('manual-new-concession');
  const createBtn = document.getElementById('manual-create-concession-btn');
  const feedbackEl = document.getElementById('manual-concession-feedback');
  const metaCard = document.getElementById('manual-meta-card');
  const tableCard = document.getElementById('manual-table-card');
  const saveArea = document.getElementById('manual-save-area');
  const addColBtn = document.getElementById('manual-add-col-btn');
  const saveBtn = document.getElementById('manual-save-btn');
  const forceCheckbox = document.getElementById('manual-force-overwrite');
  const reloadItemsBtn = document.getElementById('manual-reload-items-btn');
  const addRowBtn = document.getElementById('manual-add-row-btn');
  // ========== Chargement des concessions ==========
  async function loadConcessions() {
    showSpinner();
    try {
      const concessions = await apiCall('GET', '/concessions');
      selectEl.innerHTML = '<option value="">-- Choisir --</option>';
      concessions.forEach(c => {
        selectEl.innerHTML += `<option value="${c.id_concession}">${c.nom}</option>`;
      });
    } catch (e) {
      showToast('Erreur chargement concessions', 'danger');
    } finally {
      hideSpinner();
    }
  }

  // ========== Chargement des items existants ==========
  async function loadExistingItemsForConcession(idConcession) {
    try {
      const items = await apiCall('GET', '/items', null, { id_concession: idConcession });
      return items.map(it => it.libelle_canonique).filter(Boolean);
    } catch (e) {
      console.warn('Impossible de charger les items', e);
      return [];
    }
  }

  // ========== Chargement des colonnes existantes ==========
  async function loadExistingColumnsForConcession(idConcession) {
    try {
      const colonnes = await apiCall('GET', '/colonnes', null, { id_concession: idConcession });
      return colonnes.map(c => c.libelle_canonique);
    } catch (e) {
      console.warn('Impossible de charger les colonnes', e);
      return [];
    }
  }

  // ========== Modale des items (libellés) ==========
  function renderExistingItemsModal(libelles) {
    const container = document.getElementById('manual-items-list-container');
    if (!container) return;
    if (!libelles || libelles.length === 0) {
      container.innerHTML = '<p class="text-muted">Aucun item existant pour cette concession.</p>';
      return;
    }
    let html = '<div class="list-group">';
    libelles.forEach((lib, idx) => {
      html += `
        <label class="list-group-item d-flex align-items-center">
          <input class="form-check-input me-2 item-checkbox" type="checkbox" value="${escapeHtml(lib)}" data-idx="${idx}">
          ${escapeHtml(lib)}
        </label>`;
    });
    html += '</div>';
    container.innerHTML = html;
  }

  // ========== Modale des colonnes ==========
  function renderColumnsModal(columnNames) {
    const container = document.getElementById('manual-columns-list-container');
    if (!container) return;

    // Description toujours en premier, cochée et désactivée
    const filtered = columnNames.filter(c => c !== 'Description');
    let html = '<div class="list-group">';
    html += `
      <label class="list-group-item d-flex align-items-center">
        <input class="form-check-input me-2" type="checkbox" checked disabled>
        <strong>Description</strong> <small class="text-muted ms-2">(obligatoire)</small>
      </label>`;
    filtered.forEach(col => {
      html += `
        <label class="list-group-item d-flex align-items-center">
          <input class="form-check-input me-2 column-checkbox" type="checkbox" value="${escapeHtml(col)}">
          ${escapeHtml(col)}
        </label>`;
    });
    html += '</div>';
    container.innerHTML = html;
  }

  function escapeHtml(str) {
    return String(str).replace(/[&<>]/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[m]));
  }

  // ========== Passage à la sélection des colonnes ==========
  async function promptColumnsSelection(descriptions) {
    pendingDescriptions = descriptions;
    showSpinner();
    try {
      const colonnes = await loadExistingColumnsForConcession(manualConcessionId);
      if (colonnes.length === 0) {
        // Aucune colonne en base -> colonnes par défaut
        availableColumnNames = ['Description', 'Montant'];
        finalizeTableSetup(availableColumnNames, pendingDescriptions);
      } else {
        if (!colonnes.includes('Description')) {
          colonnes.unshift('Description');
        }
        availableColumnNames = colonnes;
        renderColumnsModal(availableColumnNames);
        const modalEl = new bootstrap.Modal(document.getElementById('manual-columns-modal'));
        modalEl.show();

        const confirmBtn = document.getElementById('manual-confirm-columns-btn');
        const handleConfirm = () => {
          const checked = document.querySelectorAll('#manual-columns-list-container .column-checkbox:checked');
          let selectedCols = Array.from(checked).map(cb => cb.value);
          if (!selectedCols.includes('Description')) {
            selectedCols.unshift('Description');
          }
          finalizeTableSetup(selectedCols, pendingDescriptions);
          modalEl.hide();
          confirmBtn.removeEventListener('click', handleConfirm);
        };
        confirmBtn.addEventListener('click', handleConfirm, { once: true });
      }
    } catch (e) {
      showToast('Erreur chargement colonnes', 'danger');
    } finally {
      hideSpinner();
    }
  }

  // ========== Finalisation : construction des colonnes + affichage du tableau ==========
function finalizeTableSetup(selectedColumns, descriptions) {
    // 1. Définir les colonnes du tableau
    buildTableColumns(selectedColumns);

    // 2. Préparer les données AVANT d’initialiser le tableau
    //    (manualEditedData sera utilisé par initManualTable)
    const newRows = descriptions.map(desc => {
        const row = { description: desc, __total_ligne: 0 };
        manualTableColumns.forEach(col => {
            if (col.field !== 'description' && col.field !== '__total_ligne') {
                row[col.field] = '';
            }
        });
        return row;
    });

    if (newRows.length === 0) {
        const emptyRow = { description: '', __total_ligne: 0 };
        manualTableColumns.forEach(col => {
            if (col.field !== 'description' && col.field !== '__total_ligne') emptyRow[col.field] = '';
        });
        newRows.push(emptyRow);
    }

    manualEditedData = newRows;

    // 3. Afficher le formulaire et initialiser le tableau
    showFormParts();

    // 4. Mettre à jour le footer et recalculer les totaux
    recalculerTotauxManuel();
    updateManualFooter();

    showToast(descriptions.length ? `${descriptions.length} article(s) prêt(s)` : 'Facture vide prête', 'success');
}

  // ========== Remplissage du tableau avec les descriptions sélectionnées ==========
  function fillManualTableWithSelectedDescriptions(descriptions) {
    const newRows = descriptions.map(desc => {
      const row = { description: desc, __total_ligne: 0 };
      manualTableColumns.forEach(col => {
        if (col.field !== 'description' && col.field !== '__total_ligne') {
          row[col.field] = '';
        }
      });
      return row;
    });

    if (newRows.length === 0) {
      const emptyRow = { description: '', __total_ligne: 0 };
      manualTableColumns.forEach(col => {
        if (col.field !== 'description' && col.field !== '__total_ligne') emptyRow[col.field] = '';
      });
      newRows.push(emptyRow);
    }

    if (manualTableInstance) {
      manualTableInstance.setData(newRows);
    } else {
      manualEditedData = newRows;
    }
    recalculerTotauxManuel();
    updateManualFooter();
  }

  // ========== Sélection d'une concession ==========
  async function selectConcession(id) {
    manualConcessionId = id;
    const option = selectEl.options[selectEl.selectedIndex];
    manualConcessionNom = option?.text || '';
    feedbackEl.innerHTML = `<div class="alert alert-success py-2">Concession sélectionnée : <strong>${manualConcessionNom}</strong></div>`;

    // Cacher les parties formulaire tant que les sélections ne sont pas faites
    metaCard.style.display = 'none';
    tableCard.style.display = 'none';
    saveArea.style.display = 'none';

    const libelles = await loadExistingItemsForConcession(id);
    manualExistingItems = libelles;

    if (libelles.length > 0) {
      renderExistingItemsModal(libelles);
      const modalEl = new bootstrap.Modal(document.getElementById('manual-items-modal'));
      modalEl.show();

      const confirmBtn = document.getElementById('manual-confirm-items-btn');
      const handleConfirm = () => {
        const checked = document.querySelectorAll('#manual-items-list-container .item-checkbox:checked');
        const selected = Array.from(checked).map(cb => cb.value);
        modalEl.hide();
        confirmBtn.removeEventListener('click', handleConfirm);
        // Passer à la sélection des colonnes
        promptColumnsSelection(selected);
      };
      confirmBtn.addEventListener('click', handleConfirm, { once: true });
    } else {
      // Aucun item → directement la sélection des colonnes avec liste vide
      promptColumnsSelection([]);
    }
  }

  // ========== Création d'une nouvelle concession ==========
  async function createConcession(nom) {
    if (!nom.trim()) return;
    showSpinner();
    try {
      const newC = await apiCall('POST', '/concessions', null, { nom: nom.trim() });
      manualConcessionId = newC.id_concession;
      manualConcessionNom = newC.nom;
      feedbackEl.innerHTML = `<div class="alert alert-success py-2">Concession créée : <strong>${manualConcessionNom}</strong></div>`;
      selectEl.innerHTML += `<option value="${newC.id_concession}">${newC.nom}</option>`;
      selectEl.value = newC.id_concession;
      newNameInput.value = '';
      // Colonnes par défaut
      buildTableColumns(['Description', 'Montant']);
      showFormParts();
      fillManualTableWithSelectedDescriptions([]);
    } catch (e) {
      showToast('Erreur création concession', 'danger');
    } finally {
      hideSpinner();
    }
  }

  // ========== Affichage des parties métadonnées + tableau ==========
  function showFormParts() {
    metaCard.style.display = 'block';
    tableCard.style.display = 'block';
    saveArea.style.display = 'flex';
    initManualTable();
  }

  // ========== Construction des colonnes Tabulator ==========
  function buildTableColumns(colNames) {
    manualTableColumns = [];
    colNames.forEach((name, index) => {
      if (index === 0) {
        manualTableColumns.push({
          title: name, field: 'description', editor: 'input', width: 250, frozen: true
        });
      } else {
        manualTableColumns.push({
          title: name, field: name, editor: 'input',
          formatter: cell => cell.getValue() !== undefined ? cell.getValue() : ''
        });
      }
    });
    manualTableColumns.push({
      title: 'Total', field: '__total_ligne',
      formatter: cell => cell.getValue()?.toFixed(2) + ' €' || '',
      editor: false, hozAlign: 'right', width: 120
    });
  }

  // ========== Initialisation du tableau Tabulator ==========
  function initManualTable() {
    if (manualTableInstance) manualTableInstance.destroy();

    let dataToUse = manualEditedData.length ? manualEditedData : null;
    if (!dataToUse) {
      const emptyRow = { description: '', __total_ligne: 0 };
      manualTableColumns.forEach(col => {
        if (col.field !== 'description' && col.field !== '__total_ligne') emptyRow[col.field] = '';
      });
      dataToUse = [emptyRow];
      manualEditedData = dataToUse;
    }

    const tableEl = document.getElementById('manual-items-table');
    manualTableInstance = new Tabulator(tableEl, {
      data: dataToUse,
      columns: manualTableColumns,
      layout: 'fitColumns',
      height: '300px',
      editable: true,
      movableColumns: true,
      addRowPos: 'bottom',
      headerMenu: [
        { label: "Renommer", action: (e, col) => renameManualColumn(col) },
        { label: "Supprimer", action: (e, col) => deleteManualColumn(col) }
      ],
      footerElement: `<div style='padding:8px;text-align:right;font-weight:bold;'>Total général : <span id='manual-total-general'>0.00 €</span></div>`
    });

    manualTableInstance.on('dataLoaded', () => recalculerTotauxManuel());
    manualTableInstance.on('cellEdited', () => {
      recalculerTotauxManuel();
      updateManualFooter();
      manualEditedData = manualTableInstance.getData();
    });
    manualTableInstance.on('rowAdded', () => manualEditedData = manualTableInstance.getData());
    setTimeout(() => recalculerTotauxManuel(), 100);
  }

  // ========== Calcul des totaux ==========
  function recalculerTotauxManuel() {
    if (!manualTableInstance) return;
    const data = manualTableInstance.getData();
    const columns = manualTableInstance.getColumns();
    const montantFields = columns.map(col => col.getField()).filter(f => f !== 'description' && f !== '__total_ligne');
    let totalGen = 0;
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
      totalGen += totalLigne;
    });
    manualTotalGeneral = totalGen;
    manualTableInstance.blockRedraw();
    try {
      data.forEach((row, idx) => {
        const rowComp = manualTableInstance.getRows()[idx];
        if (rowComp) rowComp.update({ __total_ligne: row.__total_ligne });
      });
    } finally {
      manualTableInstance.restoreRedraw();
    }
    updateManualFooter();
  }

  function updateManualFooter() {
    const span = document.getElementById('manual-total-general');
    if (span) span.textContent = manualTotalGeneral.toFixed(2) + ' €';
  }

  // ========== Gestion manuelle des colonnes ==========
  function addManualColumn() {
    const colName = prompt('Nom de la nouvelle colonne :');
    if (!colName) return;
    if (manualTableColumns.some(c => c.field === colName)) {
      alert('Cette colonne existe déjà');
      return;
    }
    const totalIndex = manualTableColumns.length - 1;
    manualTableColumns.splice(totalIndex, 0, {
      title: colName,
      field: colName,
      editor: 'input',
      formatter: cell => cell.getValue() !== undefined ? cell.getValue() : ''
    });
    manualTableInstance.setColumns(manualTableColumns);
    const currentData = manualTableInstance.getData();
    currentData.forEach(row => row[colName] = '');
    manualTableInstance.setData(currentData);
    recalculerTotauxManuel();
  }

  function renameManualColumn(column) {
    const newName = prompt('Nouveau nom :', column.getField());
    if (!newName || newName === column.getField()) return;
    const field = column.getField();
    if (field === '__total_ligne') { alert('Impossible de renommer la colonne Total.'); return; }
    const currentData = manualTableInstance.getData();
    currentData.forEach(row => {
      if (row.hasOwnProperty(field)) {
        row[newName] = row[field];
        delete row[field];
      }
    });
    const colDef = manualTableColumns.find(c => c.field === field);
    if (colDef) colDef.field = newName;
    manualTableInstance.setColumns(manualTableColumns);
    manualTableInstance.setData(currentData);
    recalculerTotauxManuel();
  }

  function deleteManualColumn(column) {
    const field = column.getField();
    if (field === '__total_ligne') { alert('Impossible de supprimer la colonne Total.'); return; }
    if (!confirm(`Supprimer la colonne "${field}" ?`)) return;
    const currentData = manualTableInstance.getData();
    currentData.forEach(row => delete row[field]);
    manualTableColumns = manualTableColumns.filter(c => c.field !== field);
    manualTableInstance.setColumns(manualTableColumns);
    manualTableInstance.setData(currentData);
    recalculerTotauxManuel();
  }

  // ========== Sauvegarde de la facture ==========
  async function saveManualFacture() {
    const date = document.getElementById('manual-date')?.value;
    const devise = document.getElementById('manual-devise')?.value || 'TND';
    const numero = document.getElementById('manual-numero')?.value;
    const force = forceCheckbox?.checked || false;

    if (!manualConcessionId) {
      showToast('Aucune concession sélectionnée', 'danger');
      return;
    }
    const currentData = manualTableInstance.getData();
    if (currentData.length === 0) {
      showToast('Ajoutez au moins un article', 'warning');
      return;
    }
    const itemsData = currentData.map(row => {
      const { description, __total_ligne, ...valeurs } = row;
      const cleanedValeurs = {};
      Object.entries(valeurs).forEach(([k, v]) => {
        if (v !== undefined && v !== null && v !== '') cleanedValeurs[k] = String(v);
      });
      return { description: description || '', valeurs: cleanedValeurs };
    });
    const facturePayload = {
      fichier_source: 'saisie_manuelle',
      date_facture: date || null,
      devise,
      id_concession: manualConcessionId,
      nom_concession: manualConcessionNom,
      numero_facture: numero || null,
      total_montant: manualTotalGeneral || 0
    };
    const payload = { facture: facturePayload, items_data: itemsData };
    showSpinner();
    try {
      await apiCall('POST', '/facture', payload, { force });
      showToast('Facture enregistrée avec succès', 'success');
      resetForm();
    } catch (e) {
      if (e.response?.status === 409) {
        showToast('Cette facture existe déjà. Cochez "Écraser si existe" pour forcer.', 'warning');
      } else {
        showToast('Erreur lors de l\'enregistrement', 'danger');
      }
    } finally {
      hideSpinner();
    }
  }

  // ========== Réinitialisation du formulaire ==========
  function resetForm() {
    document.getElementById('manual-date').value = '';
    document.getElementById('manual-devise').value = 'TND';
    document.getElementById('manual-numero').value = '';
    forceCheckbox.checked = false;
    if (manualTableInstance) {
      manualTableInstance.destroy();
      manualTableInstance = null;
    }
    metaCard.style.display = 'none';
    tableCard.style.display = 'none';
    saveArea.style.display = 'none';
    manualEditedData = [];
  }

  // ========== Événements ==========
  selectEl.addEventListener('change', () => {
    const val = selectEl.value;
    if (val) selectConcession(parseInt(val));
    else { resetForm(); feedbackEl.innerHTML = ''; }
  });
  createBtn.addEventListener('click', () => createConcession(newNameInput.value));
  newNameInput.addEventListener('keypress', e => { if (e.key === 'Enter') createConcession(newNameInput.value); });
  addColBtn.addEventListener('click', addManualColumn);
  saveBtn.addEventListener('click', saveManualFacture);
addRowBtn?.addEventListener('click', () => {
if (!manualTableInstance) {
    showToast('Le tableau n’est pas encore prêt', 'warning');
    return;
}
// Crée une ligne vide avec les colonnes actuelles (valeurs vides)
const emptyRow = { description: '', __total_ligne: 0 };
manualTableColumns.forEach(col => {
    if (col.field !== 'description' && col.field !== '__total_ligne') {
    emptyRow[col.field] = '';
    }
});
manualTableInstance.addRow(emptyRow, true); // true = ajouter en bas
recalculerTotauxManuel();
updateManualFooter();
});

  if (reloadItemsBtn) {
    reloadItemsBtn.addEventListener('click', async () => {
      if (!manualConcessionId) { showToast('Sélectionnez une concession', 'warning'); return; }
      const libelles = await loadExistingItemsForConcession(manualConcessionId);
      if (!libelles.length) { showToast('Aucun item existant', 'info'); return; }
      renderExistingItemsModal(libelles);
      const modalEl = new bootstrap.Modal(document.getElementById('manual-items-modal'));
      modalEl.show();
      const confirmBtn = document.getElementById('manual-confirm-items-btn');
      const handleConfirm = () => {
        const checked = document.querySelectorAll('#manual-items-list-container .item-checkbox:checked');
        const selected = Array.from(checked).map(cb => cb.value);
        fillManualTableWithSelectedDescriptions(selected);
        modalEl.hide();
        confirmBtn.removeEventListener('click', handleConfirm);
      };
      confirmBtn.addEventListener('click', handleConfirm, { once: true });
    });
  }

  loadConcessions();
}