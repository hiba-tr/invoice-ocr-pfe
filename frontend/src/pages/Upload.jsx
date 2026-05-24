// Upload.jsx - Version complète corrigée
import { useState, useRef, useEffect, useCallback } from 'react';
import { useApp } from '../context/AppContext';
import { apiCall } from '../api/api';
import axios from 'axios';
import { TabulatorFull as Tabulator } from 'tabulator-tables';
import 'tabulator-tables/dist/css/tabulator.min.css';
import SemanticValidation from '../components/SemanticValidation';
import {
  UploadCloud, Save, Plus, Columns,
  Sparkles, FileText, X, Brain
} from 'lucide-react';

const API_BASE = 'http://localhost:8000';

const cleanValue = (val) => {
  if (val === null || val === undefined) return '';
  if (typeof val === 'number') return String(val);
  return String(val).replace(/\s+/g, ' ').trim();
};

export default function Upload() {
  const { showSpinner, hideSpinner, showToast, concessionsList, setConcessionsList } = useApp();

  // ---- États communs ----
  const [files, setFiles] = useState([]);
  const [extraction, setExtraction] = useState(null);
  const [concessionId, setConcessionId] = useState('');
  const [newConcessionName, setNewConcessionName] = useState('');
  const [meta, setMeta] = useState({
    date: '',
    fournisseur: '',
    fournisseurId: '',
    currency: 'EUR',
    company: ''
  });
  const [forceOverwrite, setForceOverwrite] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [headerMenu, setHeaderMenu] = useState({
    visible: false,
    column: null,
    table: null,
    x: 0,
    y: 0,
  });
  const [extraMeta, setExtraMeta] = useState({});
  const [selectedMeta, setSelectedMeta] = useState({});
  const [candidateTexts, setCandidateTexts] = useState([]);
  const [checkedCandidates, setCheckedCandidates] = useState({});
  
  // ---- États pour la validation unifiée ----
  const [showValidation, setShowValidation] = useState(false);
  const [validationData, setValidationData] = useState({
    columns: [],
    items: [],
    existingItems: [],
    existingColumns: []
  });

  // ---- Tabulator multi‑tables ----
  const tablesContainerRef = useRef(null);
  const tabulatorInstances = useRef({});
  const primaryTable = useRef(null);
  const fileInputRef = useRef(null);
  const [supplierList, setSupplierList] = useState([]);
  
  // ---- Stocker les informations originales des sections ----
  const sectionsMetadataRef = useRef([]);

  const frozenColumnStyle = `
    .tabulator .tabulator-frozen-left {
      z-index: 10 !important;
      background-color: #ffffff !important;
    }
    .tabulator .tabulator-frozen-left .tabulator-cell {
      background-color: #ffffff !important;
      border-right: 2px solid #e2e8f0 !important;
    }
    .tabulator-row .tabulator-frozen-left {
      background-color: #ffffff !important;
    }
    .tabulator-row:nth-child(even) .tabulator-frozen-left {
      background-color: #f8fafc !important;
    }
    .tabulator-row:nth-child(even) .tabulator-frozen-left .tabulator-cell {
      background-color: #f8fafc !important;
    }
  `;

  // ---- Charger la liste des concessions au montage ----
  useEffect(() => {
    apiCall('GET', '/concessions')
      .then(setConcessionsList)
      .catch(() => {});
  }, [setConcessionsList]);

  useEffect(() => {
    apiCall('GET', '/fournisseurs')
      .then(setSupplierList)
      .catch(() => {});
  }, []);

  // ---- Fermer le menu contextuel au clic extérieur ----
  useEffect(() => {
    const handler = () => setHeaderMenu(prev => ({ ...prev, visible: false }));
    document.addEventListener('click', handler);
    return () => document.removeEventListener('click', handler);
  }, []);

  // ---- Gestion des fichiers ----
  const handleFiles = (newFiles) => {
    setFiles(prev => [...prev, ...Array.from(newFiles)]);
  };

  const removeFile = (index) => {
    setFiles(prev => prev.filter((_, i) => i !== index));
  };

  // ---- Extraction (POST /upload classique) ----
  const handleExtract = async () => {
    if (!files.length) {
      showToast("Veuillez d'abord choisir un fichier !", 'warning');
      return;
    }

    showSpinner();
    try {
      const formData = new FormData();
      formData.append('file', files[0]);
      const resp = await axios.post(`${API_BASE}/upload`, formData);
      setExtraction(resp.data);
      showToast('Extraction réussie !', 'success');
    } catch (err) {
      showToast('Échec de l’extraction', 'danger');
    } finally {
      hideSpinner();
    }
  };

  // ---- Création de concession ----
  const handleCreateConcession = async () => {
    if (!newConcessionName.trim()) return;
    try {
      const newC = await apiCall('POST', '/concessions', { nom: newConcessionName.trim() });
      setConcessionsList(prev => [...prev, newC]);
      setConcessionId(newC.id_concession);
      setNewConcessionName('');
      showToast('Concession créée', 'success');
    } catch {
      showToast('Erreur création concession', 'danger');
    }
  };

  // ---- Reconnaissance automatique de concession ----
  useEffect(() => {
    if (!extraction?.identity?.concession) return;

    const autoMatch = async () => {
      try {
        const match = await apiCall('GET', '/match-concession', null, {
          nom_extrait: extraction.identity.concession
        });
        if (match.matched) {
          setConcessionId(match.concession_id);
          showToast(`Concession reconnue : ${match.concession_nom}`, 'info');
          setTimeout(() => autoApplySuggestions(match.concession_id), 500);
        }
      } catch {}
    };
    autoMatch();
  }, [extraction]);

  // ---- Reconnaissance automatique du fournisseur ----
  useEffect(() => {
    if (!extraction) return;
    const incoming = extraction.extra_metadata || {};
    setExtraMeta(incoming);
    const preselected = {};
    Object.keys(incoming).forEach(key => { preselected[key] = true; });
    setSelectedMeta(preselected);

    const candidates = extraction.candidate_texts || [];
    setCandidateTexts(candidates);
    const checked = {};
    candidates.forEach((_, i) => { checked[i] = true; });
    setCheckedCandidates(checked);
  }, [extraction]);

  // ---- Suggestions automatiques après reconnaissance ----
  const autoApplySuggestions = async (cid) => {
    const instances = Object.values(tabulatorInstances.current);
    let updated = 0;
    for (const table of instances) {
      const data = table.getData();
      for (let i = 0; i < data.length; i++) {
        const desc = data[i].description;
        if (!desc) continue;
        try {
          const resp = await apiCall('GET', '/suggest', null, {
            description: desc,
            id_concession: cid
          });
          if (resp.item_id) {
            table.updateData([{ id: data[i].id, description: resp.libelle_canonique }]);
            updated++;
          }
        } catch {}
      }
    }
    if (updated > 0) showToast(`${updated} article(s) harmonisé(s)`, 'info');
  };

  // ---- Recalcul des totaux pour une table donnée ----
  const recalculateTotalsForTable = useCallback((table) => {
    if (!table) return;
    const data = table.getData();
    const cols = table.getColumns();
    const numericFields = cols
      .map(c => c.getField())
      .filter(f => f !== 'description' && f !== '__total_ligne');

    let totalGeneral = 0;
    data.forEach(row => {
      let totalLigne = 0;
      numericFields.forEach(f => {
        const val = row[f];
        if (val !== undefined && val !== null && val !== '') {
          const num = parseFloat(String(val).replace(',', '.'));
          if (!isNaN(num)) totalLigne += num;
        }
      });
      row.__total_ligne = totalLigne;
      totalGeneral += totalLigne;
    });

    table.blockRedraw();
    try {
      data.forEach((row, idx) => {
        const rowComp = table.getRows()[idx];
        if (rowComp) rowComp.update({ __total_ligne: row.__total_ligne });
      });
    } finally {
      table.restoreRedraw();
    }
    const footerSpan = document.getElementById(`total-general-footer-${table._docoreIdx ?? 'main'}`);
    if (footerSpan) footerSpan.textContent = totalGeneral.toFixed(2) + ' €';
  }, []);

  // ==================== FONCTIONS DE MATCHING SÉMANTIQUE ====================
  
  const enrichirColonnesAvecMatching = async (sections, concessionId) => {
    if (!sections || sections.length === 0) return [];
    
    const colonnesAVerifier = [];
    
    for (const section of sections) {
      const headers = section.columns?.headers || [];
      
      for (const header of headers) {
        try {
          const suggestion = await apiCall('GET', '/suggest/column', null, {
            column_name: header,
            id_concession: concessionId
          });
          
          colonnesAVerifier.push({
            original: header,
            section: section.name || 'Section principale',
            suggested: suggestion.item_id ? {
              id_colonne: suggestion.item_id,
              libelle_canonique: suggestion.libelle_canonique
            } : null,
            confiance: suggestion.confiance || 0
          });
        } catch (error) {
          console.warn(`Erreur matching pour colonne ${header}:`, error);
          colonnesAVerifier.push({
            original: header,
            section: section.name || 'Section principale',
            suggested: null,
            confiance: 0
          });
        }
      }
    }
    
    return colonnesAVerifier;
  };

  // ---- Validation sémantique unifiée (colonnes + items) ----
  const handleSemanticValidation = async () => {
    if (!concessionId) {
      showToast('⚠️ Sélectionnez une Concession.', 'warning');
      return;
    }

    showSpinner();
    try {
      const sections = extraction.sections || [];
      const columnsToValidate = await enrichirColonnesAvecMatching(sections, concessionId);
      
      // Récupérer les items depuis les instances Tabulator (données modifiées)
      const itemsData = [];
      for (const [sectionIdx, table] of Object.entries(tabulatorInstances.current)) {
        const tableData = table.getData();
        
        for (const row of tableData) {
          let description = '';
          
          // Chercher la description dans les colonnes
          for (const [key, value] of Object.entries(row)) {
            if (key !== '__total_ligne' && key !== '_actions' && value && String(value).trim().length > 0) {
              description = String(value).trim();
              break;
            }
          }
          
          if (!description) continue;
          
          itemsData.push({
            description: description,
            valeurs: {}
          });
        }
      }
      
      // Validation sémantique des items
      const validationResults = [];
      for (const item of itemsData) {
        if (!item.description) continue;
        try {
          const result = await apiCall('GET', '/suggest/confirm', null, {
            description: item.description,
            id_concession: concessionId
          });
          validationResults.push({ 
            ...item, 
            semantic: result,
            originalDescription: item.description
          });
        } catch (error) {
          console.error(`Erreur pour ${item.description}:`, error);
          validationResults.push({ 
            ...item, 
            semantic: { needs_confirmation: false, auto_match: false },
            originalDescription: item.description
          });
        }
      }

      const existingItems = await apiCall('GET', '/items', null, { id_concession: concessionId });
      const existingColumns = await apiCall('GET', '/colonnes', null, { id_concession: concessionId });
      
      setValidationData({
        columns: columnsToValidate,
        items: validationResults,
        existingItems: existingItems,
        existingColumns: existingColumns
      });
      
      setShowValidation(true);
      
    } catch (error) {
      console.error('Erreur validation sémantique:', error);
      showToast('Erreur lors de la validation sémantique', 'danger');
    } finally {
      hideSpinner();
    }
  };

  // ---- Sauvegarde de la facture avec les données modifiées ----
  const saveFacture = async (combinedDecisions) => {
    if (!concessionId) {
      showToast('⚠️ Sélectionnez une Concession.', 'warning');
      return;
    }

    showSpinner();

    try {
      const itemDecisions = combinedDecisions?.items || {};
      
      const sectionsPayload = [];
      
      for (const [sectionIdx, table] of Object.entries(tabulatorInstances.current)) {
        const sectionMetadata = sectionsMetadataRef.current[parseInt(sectionIdx)];
        if (!sectionMetadata) continue;
        
        const tableData = table.getData();
        const columnsDef = table.getColumnDefinitions();
        
        // Récupérer les en-têtes actuels (après renommage)
        const currentHeaders = [];
        const currentFields = [];
        
        for (const col of columnsDef) {
          if (col.field !== '__total_ligne' && col.field !== '_actions') {
            if (col.title && col.title.trim().length > 0) {
              currentHeaders.push(col.title);
              currentFields.push(col.field);
            }
          }
        }
        
        if (currentHeaders.length === 0) {
          console.warn(`Section ${sectionIdx} ignorée car sans colonnes valides`);
          continue;
        }
        
        // Construire les colonnes
        const colonnesPayload = [];
        for (let idx = 0; idx < currentHeaders.length; idx++) {
          const header = currentHeaders[idx];
          if (!header || header.trim() === '') continue;
          
          colonnesPayload.push({
            header: header,
            ordre: idx,
            semantic_decision: 'new',
            semantic_target_id: null
          });
        }
        
        // Construire les items avec leurs VALEURS
        const itemsPayload = [];
        for (const row of tableData) {
          let description = '';
          let descriptionField = null;
          
          // Trouver la description
          for (const field of currentFields) {
            const val = row[field];
            if (val && String(val).trim().length > 0) {
              description = String(val).trim();
              descriptionField = field;
              break;
            }
          }
          
          if (!description) continue;
          
          // Récupérer les valeurs pour TOUTES les colonnes
          const valeurs = {};
          for (let idx = 0; idx < currentFields.length; idx++) {
            const field = currentFields[idx];
            const header = currentHeaders[idx];
            const value = row[field];
            
            if (value !== undefined && value !== null && value !== '') {
              valeurs[header] = String(value).trim();
            }
          }
          
          // Trouver la décision sémantique
          let itemDecision = { decision: 'new', targetId: null };
          for (const [origIdx, decision] of Object.entries(itemDecisions)) {
            const validationItem = validationData.items[parseInt(origIdx)];
            if (validationItem && validationItem.description === description) {
              itemDecision = decision;
              break;
            }
          }
          
          itemsPayload.push({
            description: description,
            valeurs: valeurs,
            semantic_decision: itemDecision.decision,
            semantic_target_id: itemDecision.decision === 'link' ? itemDecision.targetId : null
          });
        }
        
        if (itemsPayload.length === 0) {
          console.warn(`Section ${sectionIdx} ignorée car sans items valides`);
          continue;
        }
        
        sectionsPayload.push({
          titre: sectionMetadata.sectionName || `Tableau ${parseInt(sectionIdx) + 1}`,
          colonnes: colonnesPayload,
          items_data: itemsPayload
        });
      }
      
      if (sectionsPayload.length === 0) {
        showToast('❌ Aucune donnée valide à enregistrer.', 'warning');
        return;
      }
      
      // Calculer le total général
      let grandTotal = 0;
      Object.values(tabulatorInstances.current).forEach(table => {
        table.getData().forEach(row => {
          grandTotal += row.__total_ligne || 0;
        });
      });

      const selectedCandidates = candidateTexts.filter((_, i) => checkedCandidates[i] !== false);

      const payload = {
        facture: {
          fichier_source: files[0]?.name || 'Saisie Manuelle',
          date_facture: meta.date || null,
          devise: meta.currency || 'EUR',
          id_concession: parseInt(concessionId),
          fournisseur: meta.fournisseur || '',
          total_montant: grandTotal,
          extra_metadata: JSON.stringify(selectedCandidates)
        },
        sections: sectionsPayload
      };

      console.log('📤 Envoi facture:', JSON.stringify(payload, null, 2));

      await apiCall('POST', '/facture', payload, { force: forceOverwrite });
      showToast('✅ Facture enregistrée avec succès !', 'success');
      setExtraction(null);
      setFiles([]);
      setShowValidation(false);
      setValidationData({
        columns: [],
        items: [],
        existingItems: [],
        existingColumns: []
      });
    } catch (err) {
      if (err?.response?.status === 409) {
        showToast('Cette facture existe déjà. Cochez "Écraser si existe".', 'warning');
      } else {
        console.error('❌ Erreur sauvegarde:', err);
        showToast('❌ Erreur lors de la sauvegarde.', 'danger');
      }
    } finally {
      hideSpinner();
    }
  };

  // ---- Fonction pour construire une table pour une section ----
  const createTableForSection = useCallback((section, sectionIndex, globalColumns) => {
    const sectionSchema = section.columns || globalColumns;
    if (!sectionSchema || !sectionSchema.headers || sectionSchema.headers.length === 0) return null;

    const headers = sectionSchema.headers;
    const semantics = sectionSchema.semantics || [];

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

    const createTitleFormatter = () => (cell) => {
      const currentTitle = cell.getColumn().getDefinition().title;
      const span = document.createElement('span');
      span.innerHTML = currentTitle;
      span.style.marginRight = '6px';
      span.style.fontWeight = '600';
      span.style.fontSize = '13px';
      const btn = document.createElement('button');
      btn.innerHTML = '⋮';
      btn.className = 'header-menu-trigger';
      btn.style.background = 'none';
      btn.style.border = 'none';
      btn.style.cursor = 'pointer';
      btn.style.padding = '0 4px';
      btn.style.color = '#64748b';
      btn.style.fontSize = '18px';
      btn.style.lineHeight = '1';
      btn.title = 'Options de colonne';
      btn.onclick = (e) => {
        e.stopPropagation();
        const rect = btn.getBoundingClientRect();
        setHeaderMenu({
          visible: true,
          column: cell.getColumn(),
          table: cell.getColumn().getTable(),
          x: rect.left,
          y: rect.bottom + 4,
        });
      };
      const container = document.createElement('span');
      container.style.display = 'inline-flex';
      container.style.alignItems = 'center';
      container.appendChild(span);
      container.appendChild(btn);
      return container;
    };

    const columns = headers.map((header, index) => {
      const field = uniqueFields[index];
      const isDescription = field === 'description' || field === 'designation' || field === 'libelle' || field === 'article' || field === 'item';
      return {
        title: header,
        field: field,
        editor: 'input',
        minWidth: isDescription ? 250 : 140,
        frozen: isDescription,
        formatter: function(cell) {
          const val = cell.getValue();
          if (val && typeof val === 'object' && val.raw !== undefined) {
            return val.raw;
          }
          return val !== undefined && val !== null ? val : '';
        },
        titleFormatter: createTitleFormatter()
      };
    });

    columns.push({
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

    columns.push({
      title: '',
      field: '_actions',
      headerSort: false,
      hozAlign: 'center',
      width: 50,
      editor: false,
      formatter: function(cell) {
        const btn = document.createElement('button');
        btn.innerHTML = '🗑️';
        btn.style.background = 'none';
        btn.style.border = 'none';
        btn.style.cursor = 'pointer';
        btn.style.fontSize = '16px';
        btn.style.opacity = '0.5';
        btn.style.transition = 'opacity 0.2s';
        btn.title = 'Supprimer la ligne';
        btn.onmouseover = () => { btn.style.opacity = '1'; };
        btn.onmouseout = () => { btn.style.opacity = '0.5'; };
        btn.onclick = (e) => {
          e.stopPropagation();
          if (confirm('Supprimer cette ligne ?')) {
            const row = cell.getRow();
            if (row) {
              const tbl = row.getTable();
              row.delete();
              recalculateTotalsForTable(tbl);
            }
          }
        };
        return btn;
      }
    });

    const items = section.items || [];
    const tableData = items.map((it, idx) => {
      const row = { __total_ligne: 0 };
      const descField = uniqueFields.find((f, i) =>
        semantics[i] === 'description' || semantics[i] === 'designation' || semantics[i] === 'libelle' || semantics[i] === 'article' || semantics[i] === 'item'
      ) || uniqueFields[0];
      if (descField) {
        row[descField] = it.description;
      }
      if (it.amounts) {
        Object.entries(it.amounts).forEach(([sem, val]) => {
          const idx = semantics.indexOf(sem);
          if (idx !== -1) {
            const field = uniqueFields[idx];
            if (field !== descField) {
              row[field] = val?.raw !== undefined ? val.raw : (val?.value !== undefined ? val.value : val);
            }
          } else {
            if (sem !== descField) {
              row[sem] = val?.raw !== undefined ? val.raw : (val?.value !== undefined ? val.value : val);
            }
          }
        });
      }
      return row;
    });

    return { 
      columns, 
      tableData, 
      headers, 
      uniqueFields, 
      sectionName: section.name || `Tableau ${sectionIndex + 1}`,
      originalHeaders: [...headers]
    };
  }, [recalculateTotalsForTable]);

  // ---- Initialisation de toutes les tables après extraction ----
  useEffect(() => {
    if (!extraction || !tablesContainerRef.current || showValidation) return;

    Object.values(tabulatorInstances.current).forEach(t => t.destroy());
    tabulatorInstances.current = {};
    primaryTable.current = null;
    sectionsMetadataRef.current = [];

    const sections = extraction.sections || [];
    const globalColumns = extraction.columns;

    tablesContainerRef.current.innerHTML = '';

    sections.forEach((section, idx) => {
      const config = createTableForSection(section, idx, globalColumns);
      if (!config) return;

      sectionsMetadataRef.current[idx] = {
        sectionName: config.sectionName,
        originalHeaders: config.originalHeaders,
        sectionIndex: idx
      };

      const sectionDiv = document.createElement('div');
      sectionDiv.className = 'card-custom mb-3';
      sectionDiv.innerHTML = `
        <h5 class="fw-bold mb-3" style="font-family:var(--font-display);">${config.sectionName}</h5>
        <div id="items-table-${idx}" style="min-height:200px;"></div>
        <div style='padding:8px; text-align:right; font-weight:bold;'>Total général : <span id='total-general-footer-${idx}'>0.00 €</span></div>
      `;
      tablesContainerRef.current.appendChild(sectionDiv);

      setTimeout(() => {
        const tableEl = document.getElementById(`items-table-${idx}`);
        if (!tableEl) return;

        const table = new Tabulator(tableEl, {
          data: config.tableData,
          columns: config.columns,
          layout: 'fitColumns',
          height: '400px',
          editable: true,
          movableColumns: true,
        });

        tabulatorInstances.current[idx] = table;
        table._docoreIdx = idx;
        if (idx === 0) primaryTable.current = table;

        table.on('dataLoaded', () => recalculateTotalsForTable(table));
        table.on('cellEdited', () => recalculateTotalsForTable(table));
        setTimeout(() => recalculateTotalsForTable(table), 50);
      }, 10);
    });
  }, [extraction, createTableForSection, recalculateTotalsForTable, showValidation]);

  // Remplir automatiquement les champs de métadonnées depuis l'extraction
  useEffect(() => {
    if (!extraction?.identity) return;
    const ident = extraction.identity;
    setMeta(prev => ({
      ...prev,
      date: ident.period_normalized || ident.period || prev.date,
      fournisseur: ident.company || prev.fournisseur,
      currency: ident.currency || prev.currency,
    }));
  }, [extraction]);

  // ---- Opérations sur les colonnes ----
  const addColumn = () => {
    const table = primaryTable.current;
    if (!table) return;
    const colName = prompt('Nom de la nouvelle colonne :');
    if (!colName || !colName.trim()) return;

    const existingFields = table.getColumns().map(c => c.getField());
    if (existingFields.includes(colName.trim())) {
      alert('Cette colonne existe déjà');
      return;
    }

    const allDefs = table.getColumnDefinitions();
    const dataColumns = allDefs.filter(
      def => def.field !== '__total_ligne' && def.field !== '_actions'
    );
    const totalCol = allDefs.find(def => def.field === '__total_ligne');
    const actionsCol = allDefs.find(def => def.field === '_actions');

    const newColDef = {
      title: colName.trim(),
      field: colName.trim(),
      editor: 'input',
      width: 120,
    };

    const updatedDefs = [
      ...dataColumns,
      newColDef,
      totalCol,
      actionsCol,
    ].filter(Boolean);

    const data = table.getData();
    data.forEach(row => row[colName.trim()] = '');
    table.setColumns(updatedDefs);
    table.setData(data);
    recalculateTotalsForTable(table);
  };

  const addRow = () => {
    const table = primaryTable.current;
    if (!table) return;
    const desc = prompt('Description de la nouvelle ligne :');
    if (desc === null) return;
    if (!desc.trim()) {
      showToast('La description est obligatoire.', 'warning');
      return;
    }
    const cols = table.getColumns().filter(c => c.getField() !== '__total_ligne' && c.getField() !== '_actions');
    const rowData = { __total_ligne: 0 };
    cols.forEach(col => { rowData[col.getField()] = ''; });
    const frozenCol = cols.find(c => c.getDefinition().frozen);
    if (frozenCol) {
      rowData[frozenCol.getField()] = desc.trim();
    } else if (cols.length > 0) {
      rowData[cols[0].getField()] = desc.trim();
    }
    table.addRow(rowData, false);
    recalculateTotalsForTable(table);
  };

  const renameColumn = (column, table) => {
    if (column.getField() === '__total_ligne') {
      alert('Impossible de renommer la colonne Total.');
      return;
    }
    const newName = prompt('Nouveau nom :', column.getDefinition().title);
    if (!newName || newName.trim() === column.getField()) return;

    const oldField = column.getField();
    const data = table.getData();
    data.forEach(row => {
      if (row.hasOwnProperty(oldField)) {
        row[newName.trim()] = row[oldField];
        delete row[oldField];
      }
    });

    const colDefs = table.getColumnDefinitions();
    const targetCol = colDefs.find(def => def.field === oldField);
    if (targetCol) {
      targetCol.title = newName.trim();
      targetCol.field = newName.trim();
    }

    table.setColumns(colDefs);
    table.setData(data);
    recalculateTotalsForTable(table);
  };

  const deleteColumn = (column, table) => {
    const field = column.getField();
    if (field === '__total_ligne') {
      alert('Impossible de supprimer la colonne Total.');
      return;
    }
    if (!confirm(`Supprimer la colonne "${column.getDefinition().title}" ?`)) return;

    table.deleteColumn(field);
    recalculateTotalsForTable(table);
  };

  const getAllTablesData = useCallback(() => {
    const allData = [];
    Object.entries(tabulatorInstances.current).forEach(([sectionIdx, table]) => {
      const data = table.getData();
      data.forEach(row => {
        const { __total_ligne, ...rest } = row;
        let description = (
          rest.description ||
          rest.designation ||
          rest.libelle ||
          rest.article ||
          rest.item ||
          ''
        ).trim();

        if (!description) {
          for (const key of Object.keys(rest)) {
            const val = rest[key];
            if (val !== undefined && val !== null && String(val).trim() !== '') {
              description = String(val).trim();
              break;
            }
          }
        }

        if (!description) description = 'Ligne sans description';

        const valeurs = {};
        Object.entries(rest).forEach(([k, v]) => {
          if (k !== '__total_ligne' && v !== undefined && v !== null && v !== '') {
            valeurs[k] = cleanValue(v);
          }
        });

        allData.push({ description, valeurs });
      });
    });
    return allData;
  }, []);

  // ==================== RENDU ====================

  if (showValidation) {
    return (
      <div className="max-w-7xl mx-auto space-y-6 animate-slide-up">
        <SemanticValidation
          items={validationData.items}
          existingItems={validationData.existingItems}
          columns={validationData.columns}
          existingColumns={validationData.existingColumns}
          concessionId={concessionId}
          onSave={saveFacture}
          onBack={() => setShowValidation(false)}
          forceOverwrite={forceOverwrite}
          onForceOverwriteChange={setForceOverwrite}
          initialTab={validationData.columns.length > 0 ? 'columns' : 'items'}
        />
      </div>
    );
  }

  if (!extraction) {
    return (
      <div className="max-w-2xl mx-auto space-y-8 animate-fade-in">
        <style>{frozenColumnStyle}</style>
        <div className="text-center space-y-2">
          <div className="inline-flex items-center gap-2 text-xs font-mono uppercase tracking-widest text-primary-light dark:text-primary-dark">
            <span className="w-6 h-px bg-primary-light dark:bg-primary-dark" />
            Import intelligent
          </div>
          <h1 className="font-display text-3xl font-extrabold text-slate-800 dark:text-white">
            Déposer une <span className="text-primary-light dark:text-primary-dark">facture</span>
          </h1>
          <p className="text-slate-500 dark:text-slate-400">Glissez vos fichiers ou paramétrez l'extraction</p>
        </div>

        <div
          className={`upload-zone ${dragOver ? 'border-primary-light dark:border-primary-dark bg-primary-light/5 dark:bg-primary-dark/5' : ''}`}
          onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
          onDragLeave={() => setDragOver(false)}
          onDrop={(e) => { e.preventDefault(); setDragOver(false); handleFiles(e.dataTransfer.files); }}
          onClick={() => fileInputRef.current?.click()}
        >
          <UploadCloud size={48} className="mx-auto text-primary-light dark:text-primary-dark mb-4" />
          <h5 className="font-semibold text-lg text-slate-700 dark:text-slate-200 mb-2">
            {files.length ? files.map(f => f.name).join(', ') : 'Glissez votre facture ici'}
          </h5>
          <p className="text-slate-400 dark:text-slate-500 text-sm">PDF, PNG, JPG (max 10 Mo)</p>
          <input ref={fileInputRef} type="file" accept=".pdf,.png,.jpg,.jpeg" multiple className="hidden" onChange={(e) => handleFiles(e.target.files)} />
        </div>

        {files.length > 0 && (
          <div className="glass-card space-y-2">
            <h6 className="font-mono text-xs uppercase tracking-wider text-slate-500 dark:text-slate-400">📎 Fichiers sélectionnés</h6>
            {files.map((f, i) => (
              <div key={i} className="flex items-center gap-3 p-3 bg-slate-50 dark:bg-slate-800/30 rounded-xl">
                <FileText size={18} className="text-primary-light dark:text-primary-dark" />
                <span className="flex-1 text-sm truncate">{f.name}</span>
                <span className="text-xs text-slate-400">{(f.size / 1024).toFixed(1)} KB</span>
                <button onClick={(e) => { e.stopPropagation(); removeFile(i); }} className="p-1 hover:text-red-500 transition-colors">
                  <X size={16} />
                </button>
              </div>
            ))}
          </div>
        )}

        <button onClick={handleExtract} disabled={!files.length} className="btn-primary w-full text-lg py-4">
          <Sparkles size={22} />
          Lancer l'extraction IA
        </button>
      </div>
    );
  }

  const nbItems = extraction.sections?.flatMap(s => s.items || []).length || 0;
  return (
    <div className="max-w-7xl mx-auto space-y-6 animate-slide-up">
      <style>{frozenColumnStyle}</style>
      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2 text-xs font-mono uppercase tracking-wider text-emerald-600 dark:text-emerald-400">
            <span className="w-6 h-px bg-emerald-500" />
            Résultat
          </div>
          <h2 className="font-display text-2xl font-extrabold text-slate-800 dark:text-white">
            Extraction <span className="text-primary-light dark:text-primary-dark">terminée</span>
          </h2>
        </div>
        <button
          onClick={() => { setExtraction(null); setFiles([]); }}
          className="btn-glass text-sm flex items-center gap-2">
          <UploadCloud size={16} /> Nouvelle facture
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="glass kpi-card accent-cyan">
          <span className="text-2xl">📄</span>
          <span className="kpi-label">Fichier traité</span>
          <span className="font-display text-lg font-bold truncate">{files[0]?.name || '—'}</span>
        </div>
        <div className="glass kpi-card accent-green">
          <span className="text-2xl">✅</span>
          <span className="kpi-label">Articles extraits</span>
          <span className="font-display text-2xl font-bold">{nbItems}</span>
        </div>
        <div className="glass kpi-card accent-blue">
          <span className="text-2xl">💰</span>
          <span className="kpi-label">Montant total estimé</span>
          <span className="font-display text-xl font-bold text-primary-light dark:text-primary-dark">— €</span>
        </div>
      </div>

      <div className="glass-card">
        <h3 className="font-display font-bold text-lg mb-4">Métadonnées</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-xs font-mono uppercase tracking-wider text-slate-500 mb-2">Concession</label>
            <div className="flex gap-2">
              <select value={concessionId} onChange={(e) => setConcessionId(e.target.value)} className="select-glass input-glass flex-1">
                <option value="">-- Choisir --</option>
                {concessionsList.map(c => (<option key={c.id_concession} value={c.id_concession}>{c.nom}</option>))}
              </select>
              <input type="text" placeholder="Nouveau..." value={newConcessionName} onChange={(e) => setNewConcessionName(e.target.value)} className="input-glass w-32" />
              <button onClick={handleCreateConcession} className="btn-glass">Créer</button>
            </div>
          </div>
          <div>
            <label className="block text-xs font-mono uppercase tracking-wider text-slate-500 mb-2">Date</label>
            <input type="date" value={meta.date} onChange={(e) => setMeta(p => ({ ...p, date: e.target.value }))} className="input-glass" />
          </div>
          <div>
            <label className="block text-xs font-mono uppercase tracking-wider text-slate-500 mb-2">Devise</label>
            <input type="text" value={meta.currency} onChange={(e) => setMeta(p => ({ ...p, currency: e.target.value }))} className="input-glass" />
          </div>
          <div>
            <label className="block text-xs font-mono uppercase tracking-wider text-slate-500 mb-2">Fournisseur</label>
            <div className="flex gap-2">
              <select
                value={meta.fournisseurId || ''}
                onChange={(e) => {
                  const selectedId = e.target.value;
                  const supplier = supplierList.find(s => s.id_fournisseur === parseInt(selectedId));
                  setMeta(prev => ({
                    ...prev,
                    fournisseurId: selectedId,
                    fournisseur: supplier ? supplier.nom : prev.fournisseur
                  }));
                }}
                className="select-glass input-glass flex-1"
              >
                <option value="">-- Choisir --</option>
                {supplierList.map(s => (
                  <option key={s.id_fournisseur} value={s.id_fournisseur}>{s.nom}</option>
                ))}
              </select>
              <input
                type="text"
                placeholder="Nouveau..."
                id="newSupplierName"
                className="input-glass w-32"
              />
              <button
                onClick={async () => {
                  const newName = document.getElementById('newSupplierName')?.value?.trim();
                  if (!newName) return;
                  try {
                    const newSupplier = await apiCall('POST', '/fournisseurs', { nom: newName });
                    setSupplierList(prev => [...prev, newSupplier]);
                    setMeta(prev => ({
                      ...prev,
                      fournisseurId: newSupplier.id_fournisseur,
                      fournisseur: newSupplier.nom
                    }));
                    document.getElementById('newSupplierName').value = '';
                    showToast('Fournisseur créé', 'success');
                  } catch {
                    showToast('Erreur création fournisseur', 'danger');
                  }
                }}
                className="btn-glass"
              >
                Créer
              </button>
            </div>
          </div>
        </div>
      </div>

      <div className="glass-card p-4 space-y-3">
        <h3 className="font-display font-bold text-lg text-slate-800 dark:text-white flex items-center gap-2">
          <span>📋</span> Informations complémentaires
        </h3>

        {candidateTexts.length > 0 ? (
          <div className="space-y-2">
            {candidateTexts.map((text, idx) => (
              <label key={idx} className="flex items-center gap-3 p-2 hover:bg-slate-50 dark:hover:bg-slate-800/30 rounded-lg transition-colors cursor-pointer">
                <input
                  type="checkbox"
                  checked={checkedCandidates[idx] ?? true}
                  onChange={(e) => setCheckedCandidates(prev => ({ ...prev, [idx]: e.target.checked }))}
                  className="rounded border-slate-300 accent-primary-light dark:accent-primary-dark"
                />
                <span className="text-sm font-medium text-slate-700 dark:text-slate-200 break-all">{text}</span>
              </label>
            ))}
          </div>
        ) : (
          <div className="text-sm text-slate-400 italic py-2">Aucune information supplémentaire trouvée.</div>
        )}

        <div className="flex gap-2 pt-3 border-t border-slate-200 dark:border-slate-700">
          <input
            type="text"
            placeholder="Ajouter une information"
            id="newInfoText"
            className="input-glass flex-1"
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                const text = e.target.value.trim();
                if (text) {
                  const newIdx = candidateTexts.length;
                  setCandidateTexts(prev => [...prev, text]);
                  setCheckedCandidates(prev => ({ ...prev, [newIdx]: true }));
                  e.target.value = '';
                }
              }
            }}
          />
          <button
            onClick={() => {
              const input = document.getElementById('newInfoText');
              const text = input?.value.trim();
              if (text) {
                const newIdx = candidateTexts.length;
                setCandidateTexts(prev => [...prev, text]);
                setCheckedCandidates(prev => ({ ...prev, [newIdx]: true }));
                input.value = '';
              }
            }}
            className="btn-glass text-sm px-3"
          >
            + Ajouter
          </button>
        </div>
      </div>

      <div className="glass-card p-4">
        <div className="flex justify-between items-center mb-4">
          <h3 className="font-display font-bold text-lg text-slate-800 dark:text-white">Articles extraits</h3>
          <div className="flex gap-2">
            <button onClick={addColumn} className="btn-glass text-sm"><Columns size={16} /> Colonne</button>
            <button onClick={addRow} className="btn-glass text-sm"><Plus size={16} /> Ligne</button>
          </div>
        </div>
        <div ref={tablesContainerRef} className="space-y-4" />
      </div>

      <div className="glass-card flex flex-col sm:flex-row justify-between items-center gap-4">
        <label className="flex items-center gap-2 text-sm cursor-pointer">
          <input type="checkbox" checked={forceOverwrite} onChange={(e) => setForceOverwrite(e.target.checked)} className="rounded border-slate-300" />
          Écraser si existante
        </label>
        <div className="flex gap-2">
          <button onClick={handleSemanticValidation} className="btn-primary bg-gradient-to-r from-purple-500 to-blue-500">
            <Brain size={18} />
            Validation sémantique
          </button>
          <button onClick={() => saveFacture({})} className="btn-primary">
            <Save size={18} />
            Enregistrer
          </button>
        </div>
      </div>

      {headerMenu.visible && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setHeaderMenu(prev => ({ ...prev, visible: false }))} />
          <div
            className="fixed z-50 flex flex-col overflow-hidden"
            style={{
              left: Math.min(headerMenu.x, window.innerWidth - 220),
              top: headerMenu.y,
              width: 200,
              background: 'rgba(255,255,255,0.92)',
              backdropFilter: 'blur(20px)',
              WebkitBackdropFilter: 'blur(20px)',
              borderRadius: 14,
              boxShadow: '0 8px 32px rgba(0,0,0,0.13)',
              border: '1px solid rgba(200,210,230,0.45)',
              padding: '8px',
              display: 'flex',
              flexDirection: 'column',
              gap: 4,
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <button
              style={{
                width: '100%',
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                padding: '8px 12px',
                borderRadius: 8,
                border: 'none',
                background: 'transparent',
                cursor: 'pointer',
                fontSize: 13,
                color: '#334155',
              }}
              onMouseEnter={e => e.currentTarget.style.background = 'rgba(0,0,0,0.04)'}
              onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
              onClick={() => {
                renameColumn(headerMenu.column, headerMenu.table);
                setHeaderMenu(prev => ({ ...prev, visible: false }));
              }}
            >
              ✏️ Renommer
            </button>
            <button
              style={{
                width: '100%',
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                padding: '8px 12px',
                borderRadius: 8,
                border: 'none',
                background: 'transparent',
                cursor: 'pointer',
                fontSize: 13,
                color: '#ef4444',
              }}
              onMouseEnter={e => e.currentTarget.style.background = 'rgba(239,68,68,0.08)'}
              onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
              onClick={() => {
                deleteColumn(headerMenu.column, headerMenu.table);
                setHeaderMenu(prev => ({ ...prev, visible: false }));
              }}
            >
              🗑️ Supprimer
            </button>
          </div>
        </>
      )}
    </div>
  );
}