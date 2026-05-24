// Manual.jsx - Version corrigée (partie du tableau)
import { useState, useEffect } from 'react';
import { useApp } from '../context/AppContext';
import { apiCall } from '../api/api';
import {
  PenTool, Plus, Save, Building2, List, Trash2, Columns,
  X, Edit2, Check, ChevronRight, Info, Package,
  Calendar, DollarSign, User, FileText, Brain
} from 'lucide-react';
import SemanticValidation from '../components/SemanticValidation';

const primary = '#06b6d4';

const enrichirColonnesAvecMatching = async (columns, concessionId) => {
  if (!columns || columns.length === 0) return [];
  
  const colonnesAVerifier = [];
  
  for (const header of columns) {
    // Ignorer la colonne Description (obligatoire)
    if (header === 'Description') continue;
    
    try {
      const suggestion = await apiCall('GET', '/suggest/column', null, {
        column_name: header,
        id_concession: concessionId
      });
      
      colonnesAVerifier.push({
        original: header,
        section: 'Saisie manuelle',
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
        section: 'Saisie manuelle',
        suggested: null,
        confiance: 0
      });
    }
  }
  
  return colonnesAVerifier;
};

// ─── Stepper ────────────────────────────────────────────────────────────────
const steps = ['Concession', 'Métadonnées', 'Articles', 'Enregistrer'];

function Stepper({ current }) {
  return (
    <div className="flex items-center gap-0 mb-8">
      {steps.map((label, i) => (
        <div key={i} className="flex items-center flex-1 last:flex-none">
          <div className="flex flex-col items-center">
            <div className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold border-2 transition-all duration-300 ${
              i < current ? 'bg-cyan-500 border-cyan-500 text-white'
              : i === current ? 'bg-white dark:bg-slate-900 border-cyan-400 text-cyan-500'
              : 'bg-white dark:bg-slate-900 border-slate-200 dark:border-slate-700 text-slate-400'
            }`}>
              {i < current ? <Check size={14} /> : i + 1}
            </div>
            <span className={`text-xs mt-1 font-medium whitespace-nowrap ${i === current ? 'text-cyan-500' : 'text-slate-400'}`}>
              {label}
            </span>
          </div>
          {i < steps.length - 1 && (
            <div className={`flex-1 h-0.5 mx-2 mb-5 transition-all duration-500 ${i < current ? 'bg-cyan-400' : 'bg-slate-200 dark:bg-slate-700'}`} />
          )}
        </div>
      ))}
    </div>
  );
}

// ─── Modal générique ─────────────────────────────────────────────────────────
function Modal({ title, icon, onClose, children, footer }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm" onClick={onClose}>
      <div className="glass-card w-full max-w-md max-h-[80vh] flex flex-col" onClick={e => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4 flex-shrink-0">
          <h3 className="font-bold text-lg flex items-center gap-2">{icon}{title}</h3>
          <button onClick={onClose} className="p-1 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800">
            <X size={18} className="text-slate-500" />
          </button>
        </div>
        <div className="overflow-y-auto flex-1">{children}</div>
        {footer && <div className="flex-shrink-0 mt-4">{footer}</div>}
      </div>
    </div>
  );
}

// ─── Main ────────────────────────────────────────────────────────────────────
export default function Manual() {
  const { showSpinner, hideSpinner, showToast, concessionsList, setConcessionsList } = useApp();

  const [step, setStep] = useState(0);
  const [selectedConcession, setSelectedConcession] = useState('');
  const [newConcessionName, setNewConcessionName] = useState('');

  // Métadonnées
  const [meta, setMeta] = useState({ fournisseur: '', devise: 'EUR', date: '' });
  const [newFournisseurName, setNewFournisseurName] = useState('');
  const [extraInfos, setExtraInfos] = useState([]);
  const [newInfo, setNewInfo] = useState('');
  const [supplierList, setSupplierList] = useState([]);

  // Items & colonnes disponibles
  const [availableItems, setAvailableItems] = useState([]);
  const [availableCols, setAvailableCols] = useState([]);

  // Modals
  const [showItemsModal, setShowItemsModal] = useState(false);
  const [showColsModal, setShowColsModal] = useState(false);
  const [itemSearch, setItemSearch] = useState('');
  const [colSearch, setColSearch] = useState('');
  const [checkedItems, setCheckedItems] = useState({});
  const [checkedCols, setCheckedCols] = useState({});

  // Table
  const [tableColumns, setTableColumns] = useState(['Description']);
  const [tableRows, setTableRows] = useState([]);
  const [editingCell, setEditingCell] = useState(null);
  const [newColName, setNewColName] = useState('');
  const [showAddCol, setShowAddCol] = useState(false);

  const [forceOverwrite, setForceOverwrite] = useState(false);
  
  // États pour la validation sémantique
  const [showSemanticValidation, setShowSemanticValidation] = useState(false);
  const [semanticData, setSemanticData] = useState(null);

  useEffect(() => {
    apiCall('GET', '/concessions').then(setConcessionsList).catch(() => {});
    apiCall('GET', '/fournisseurs').then(setSupplierList).catch(() => {});
  }, [setConcessionsList]);

  // ── Step 0 ─────────────────────────────────────────────────────────────────
  const handleSelectConcession = async (id) => {
    if (!id) return;
    setSelectedConcession(id);
    showSpinner();
    try {
      const [items, cols] = await Promise.all([
        apiCall('GET', '/items', null, { id_concession: id }),
        apiCall('GET', '/colonnes', null, { id_concession: id }),
      ]);
      setAvailableItems(items.map(i => i.libelle_canonique).filter(Boolean));
      setAvailableCols(cols.map(c => c.libelle_canonique).filter(Boolean));
    } catch {
      setAvailableItems([]);
      setAvailableCols([]);
    } finally {
      hideSpinner();
    }
    setStep(1);
  };

  const handleCreateConcession = async () => {
    if (!newConcessionName.trim()) return;
    showSpinner();
    try {
      const c = await apiCall('POST', '/concessions', { nom: newConcessionName.trim() });
      setConcessionsList(prev => [...prev, c]);
      setNewConcessionName('');
      showToast('Concession créée', 'success');
      setAvailableItems([]);
      setAvailableCols([]);
      setSelectedConcession(c.id_concession);
      setStep(1);
    } catch {
      showToast('Erreur création concession', 'danger');
    } finally {
      hideSpinner();
    }
  };

  // ── Fournisseur ────────────────────────────────────────────────────────────
  const handleCreateFournisseur = async () => {
    if (!newFournisseurName.trim()) return;
    showSpinner();
    try {
      const f = await apiCall('POST', '/fournisseurs', { nom: newFournisseurName.trim() });
      setSupplierList(prev => [...prev, f]);
      setMeta(p => ({ ...p, fournisseur: f.nom }));
      setNewFournisseurName('');
      showToast('Fournisseur créé', 'success');
    } catch {
      showToast('Erreur création fournisseur', 'danger');
    } finally {
      hideSpinner();
    }
  };

  // ── Infos complémentaires ──────────────────────────────────────────────────
  const addExtraInfo = () => {
    if (!newInfo.trim()) return;
    setExtraInfos(prev => [...prev, newInfo.trim()]);
    setNewInfo('');
  };

  // ── Modals items/colonnes ──────────────────────────────────────────────────
  const openItemsModal = () => {
    setCheckedItems({});
    setItemSearch('');
    setShowItemsModal(true);
  };

  const openColsModal = () => {
    setCheckedCols({});
    setColSearch('');
    setShowColsModal(true);
  };

  const confirmItems = () => {
    const selected = availableItems.filter(i => checkedItems[i]);
    setShowItemsModal(false);
    if (selected.length > 0) {
      const rows = selected.map(d => {
        const r = { Description: d };
        tableColumns.slice(1).forEach(c => { r[c] = ''; });
        return r;
      });
      setTableRows(prev => [...prev, ...rows]);
    }
  };

  const confirmCols = () => {
    const selected = ['Description', ...availableCols.filter(c => checkedCols[c] && c !== 'Description')];
    setShowColsModal(false);
    setTableColumns(selected);
    setTableRows(prev => prev.map(row => {
      const newRow = { Description: row.Description || '' };
      selected.slice(1).forEach(c => { newRow[c] = row[c] || ''; });
      return newRow;
    }));
    if (tableRows.length === 0) {
      setTableRows([Object.fromEntries(selected.map(c => [c, '']))]);
    }
  };

  // ── Table ──────────────────────────────────────────────────────────────────
  const addRow = () => {
    setTableRows(prev => [...prev, Object.fromEntries(tableColumns.map(c => [c, '']))]);
  };

  const deleteRow = (i) => {
    if (tableRows.length <= 1) { showToast('Il faut au moins une ligne', 'warning'); return; }
    setTableRows(prev => prev.filter((_, idx) => idx !== i));
  };

  const updateCell = (rowIdx, col, val) => {
    setTableRows(prev => prev.map((r, i) => i === rowIdx ? { ...r, [col]: val } : r));
    setEditingCell(null);
  };

  const addColumn = () => {
    const name = newColName.trim();
    if (!name) return;
    if (tableColumns.includes(name)) { showToast('Colonne existante', 'warning'); return; }
    setTableColumns(prev => [...prev, name]);
    setTableRows(prev => prev.map(r => ({ ...r, [name]: '' })));
    setNewColName('');
    setShowAddCol(false);
  };

  const deleteColumn = (col) => {
    if (col === 'Description') { showToast('Description obligatoire', 'warning'); return; }
    setTableColumns(prev => prev.filter(c => c !== col));
    setTableRows(prev => prev.map(r => { const n = { ...r }; delete n[col]; return n; }));
  };


  const validateSemantic = async () => {
    if (!selectedConcession) {
      showToast('Sélectionnez une concession', 'warning');
      return;
    }
    
    const [descCol, ...valCols] = tableColumns;
    const itemsToValidate = tableRows
      .filter(r => r[descCol]?.trim())
      .map(r => ({
        description: r[descCol].trim(),
        valeurs: Object.fromEntries(valCols.filter(c => r[c] !== '').map(c => [c, String(r[c])])),
      }));
    
    if (itemsToValidate.length === 0) {
      showToast('Ajoutez au moins un article', 'warning');
      return;
    }
    
    showSpinner();
    try {
      // 🔥 1. Valider les colonnes (en-têtes)
      const columnsToValidate = [];
      for (const header of tableColumns) {
        // Ignorer la colonne Description (obligatoire)
        if (header === 'Description') continue;
        
        try {
          const suggestion = await apiCall('GET', '/suggest/column', null, {
            column_name: header,
            id_concession: selectedConcession
          });
          
          columnsToValidate.push({
            original: header,
            section: 'Saisie manuelle',
            suggested: suggestion.item_id ? {
              id_colonne: suggestion.item_id,
              libelle_canonique: suggestion.libelle_canonique
            } : null,
            confiance: suggestion.confiance || 0
          });
        } catch (error) {
          console.warn(`Erreur matching pour colonne ${header}:`, error);
          columnsToValidate.push({
            original: header,
            section: 'Saisie manuelle',
            suggested: null,
            confiance: 0
          });
        }
      }
      
      console.log('✅ Colonnes à valider:', columnsToValidate);
      
      // 🔥 2. Valider les items (lignes)
      const validationResults = [];
      for (const item of itemsToValidate) {
        console.log('🔍 Validation item:', item.description);
        const result = await apiCall('GET', '/suggest/confirm', null, {
          description: item.description,
          id_concession: selectedConcession
        });
        console.log('📊 Résultat pour', item.description, ':', result);
        validationResults.push({ ...item, semantic: result });
      }
      
      const existingItems = await apiCall('GET', '/items', null, { id_concession: selectedConcession });
      const existingColumns = await apiCall('GET', '/colonnes', null, { id_concession: selectedConcession });
      
      setSemanticData({
        items: validationResults,
        existingItems: existingItems,
        columns: columnsToValidate,
        existingColumns: existingColumns
      });
      setShowSemanticValidation(true);
    } catch (error) {
      console.error('❌ Erreur validation sémantique:', error);
      showToast('Erreur validation sémantique: ' + (error.message || 'Erreur inconnue'), 'danger');
    } finally {
      hideSpinner();
    }
  };


  const saveFacture = async (combinedDecisions = null) => {
    if (!selectedConcession) { 
      showToast('Sélectionnez une concession', 'warning'); 
      return; 
    }
    
    const [descCol, ...valCols] = tableColumns;
    
    // 🔥 Récupérer les décisions des colonnes (si présentes)
    const columnDecisions = combinedDecisions?.columns || {};
    
    // 🔥 Construire les colonnes avec décisions sémantiques
    const colonnesPayload = tableColumns.map((col, ordre) => {
      let semanticDecision = 'new';
      let semanticTargetId = null;
      
      // Trouver la décision pour cette colonne
      if (semanticData?.columns) {
        for (let idx = 0; idx < semanticData.columns.length; idx++) {
          const colToValidate = semanticData.columns[idx];
          const decision = columnDecisions[idx];
          if (colToValidate && colToValidate.original === col && decision) {
            semanticDecision = decision.decision;
            semanticTargetId = decision.decision === 'link' ? decision.targetId : null;
            break;
          }
        }
      }
      
      return {
        header: col,
        ordre: ordre,
        semantic_decision: semanticDecision,
        semantic_target_id: semanticTargetId
      };
    });
    
    // 🔥 Construire les items avec décisions sémantiques
    const items_data = tableRows
      .filter(r => r[descCol]?.trim())
      .map((r) => {
        let semanticDecision = 'new';
        let semanticTargetId = null;
        
        // Trouver la décision pour cet item
        if (combinedDecisions?.items && semanticData?.items) {
          for (let idx = 0; idx < semanticData.items.length; idx++) {
            const validationItem = semanticData.items[idx];
            const decision = combinedDecisions.items[idx];
            if (validationItem && validationItem.description === r[descCol].trim() && decision) {
              semanticDecision = decision.decision;
              semanticTargetId = decision.decision === 'link' ? decision.targetId : null;
              break;
            }
          }
        }
        
        return {
          description: r[descCol].trim(),
          valeurs: Object.fromEntries(valCols.filter(c => r[c] !== '').map(c => [c, String(r[c])])),
          semantic_decision: semanticDecision,
          semantic_target_id: semanticTargetId
        };
      });
    
    if (!items_data.length) { 
      showToast('Ajoutez au moins un article', 'warning'); 
      return; 
    }

    showSpinner();
    try {
      const payload = {
        facture: {
          fichier_source: 'saisie_manuelle',
          date_facture: meta.date || null,
          devise: meta.devise || 'EUR',
          id_concession: parseInt(selectedConcession),
          fournisseur: meta.fournisseur || '',
          total_montant: 0,
          extra_metadata: extraInfos.length ? JSON.stringify(extraInfos) : null,
        },
        sections: [
          {
            titre: 'Saisie manuelle',
            colonnes: colonnesPayload,
            items_data: items_data,
          }
        ],
      };
      
      console.log('📤 Payload envoyé:', JSON.stringify(payload, null, 2));
      
      await apiCall('POST', '/facture', payload, { force: forceOverwrite });
      showToast('✅ Facture enregistrée !', 'success');
      
      // Réinitialisation
      setStep(0);
      setSelectedConcession('');
      setMeta({ fournisseur: '', devise: 'EUR', date: '' });
      setExtraInfos([]);
      setTableColumns(['Description']);
      setTableRows([]);
      setShowSemanticValidation(false);
      setSemanticData(null);
    } catch (err) {
      console.error('❌ Erreur détaillée:', err);
      if (err?.response?.status === 409) {
        showToast('Facture existante. Cochez "Écraser".', 'warning');
      } else if (err?.response?.data?.detail) {
        showToast(`Erreur: ${err.response.data.detail}`, 'danger');
      } else {
        showToast(`Erreur enregistrement: ${err.message || 'Erreur inconnue'}`, 'danger');
      }
    } finally {
      hideSpinner();
    }
  };

  const filteredItems = availableItems.filter(i => i.toLowerCase().includes(itemSearch.toLowerCase()));
  const filteredCols = availableCols.filter(c => c.toLowerCase().includes(colSearch.toLowerCase()));

  // Affichage de la validation sémantique
  if (showSemanticValidation && semanticData) {
    return (
      <SemanticValidation
        items={semanticData.items}
        existingItems={semanticData.existingItems}
        columns={semanticData.columns}
        existingColumns={semanticData.existingColumns}
        concessionId={selectedConcession}
        onSave={saveFacture}
        onBack={() => {
          setShowSemanticValidation(false);
          setSemanticData(null);
        }}
        forceOverwrite={forceOverwrite}
        onForceOverwriteChange={setForceOverwrite}
        initialTab="items"
      />
    );
  }

  // ── Rendu ──────────────────────────────────────────────────────────────────
  return (
    <div className="max-w-4xl mx-auto space-y-6 animate-fade-in">

      {/* Header */}
      <div className="flex items-center gap-3">
        <PenTool size={28} style={{ color: primary }} />
        <div>
          <h1 className="font-display text-2xl font-extrabold text-slate-800 dark:text-white">Saisie manuelle</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400">Créez une facture étape par étape</p>
        </div>
      </div>

      <Stepper current={step} />

      {/* ── STEP 0 : Concession ── */}
      {step === 0 && (
        <div className="glass-card space-y-5 animate-fade-in">
          <h3 className="font-display font-bold text-lg flex items-center gap-2">
            <Building2 size={20} style={{ color: primary }} /> Choisir la concession
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-mono uppercase tracking-wider text-slate-500 mb-2">Concession existante</label>
              <select
                className="select-glass input-glass w-full"
                value={selectedConcession}
                onChange={e => handleSelectConcession(e.target.value)}
              >
                <option value="">-- Choisir --</option>
                {concessionsList.map(c => (
                  <option key={c.id_concession} value={c.id_concession}>{c.nom}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs font-mono uppercase tracking-wider text-slate-500 mb-2">Ou créer une nouvelle</label>
              <div className="flex gap-2">
                <input
                  className="input-glass flex-1"
                  placeholder="Nom de la concession"
                  value={newConcessionName}
                  onChange={e => setNewConcessionName(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && handleCreateConcession()}
                />
                <button onClick={handleCreateConcession} className="btn-primary px-4">Créer</button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── STEP 1 : Métadonnées ── */}
      {step === 1 && (
        <div className="space-y-5 animate-fade-in">
          <div className="glass-card space-y-4">
            <h3 className="font-display font-bold text-lg flex items-center gap-2">
              <FileText size={20} style={{ color: primary }} /> Métadonnées
            </h3>

            <div>
              <label className="block text-xs font-mono uppercase tracking-wider text-slate-500 mb-2 flex items-center gap-1">
                <User size={12} /> Fournisseur
              </label>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <select
                  className="select-glass input-glass"
                  value={meta.fournisseur}
                  onChange={e => setMeta(p => ({ ...p, fournisseur: e.target.value }))}
                >
                  <option value="">-- Choisir un fournisseur --</option>
                  {supplierList.map(s => (
                    <option key={s.id_fournisseur} value={s.nom}>{s.nom}</option>
                  ))}
                </select>
                <div className="flex gap-2">
                  <input
                    className="input-glass flex-1"
                    placeholder="Nouveau fournisseur…"
                    value={newFournisseurName}
                    onChange={e => setNewFournisseurName(e.target.value)}
                    onKeyDown={e => e.key === 'Enter' && handleCreateFournisseur()}
                  />
                  <button onClick={handleCreateFournisseur} className="btn-glass px-3 whitespace-nowrap">Créer</button>
                </div>
              </div>
              {meta.fournisseur && (
                <p className="text-xs text-cyan-600 dark:text-cyan-400 mt-1">✓ Sélectionné : <strong>{meta.fournisseur}</strong></p>
              )}
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-mono uppercase tracking-wider text-slate-500 mb-2 flex items-center gap-1">
                  <Calendar size={12} /> Date
                </label>
                <input
                  type="date"
                  className="input-glass w-full"
                  value={meta.date}
                  onChange={e => setMeta(p => ({ ...p, date: e.target.value }))}
                />
              </div>
              <div>
                <label className="block text-xs font-mono uppercase tracking-wider text-slate-500 mb-2 flex items-center gap-1">
                  <DollarSign size={12} /> Devise
                </label>
                <input
                  className="input-glass w-full"
                  placeholder="EUR"
                  value={meta.devise}
                  onChange={e => setMeta(p => ({ ...p, devise: e.target.value }))}
                />
              </div>
            </div>
          </div>

          <div className="glass-card space-y-3">
            <h3 className="font-display font-bold text-base flex items-center gap-2">
              <Info size={18} style={{ color: primary }} /> Informations complémentaires
            </h3>
            {extraInfos.length > 0 && (
              <div className="space-y-2">
                {extraInfos.map((info, i) => (
                  <div key={i} className="flex items-center gap-2 p-2 bg-slate-50 dark:bg-slate-800/40 rounded-lg text-sm">
                    <span className="text-cyan-400">•</span>
                    <span className="flex-1 text-slate-700 dark:text-slate-300">{info}</span>
                    <button onClick={() => setExtraInfos(prev => prev.filter((_, idx) => idx !== i))} className="text-slate-400 hover:text-red-400 transition-colors">
                      <X size={14} />
                    </button>
                  </div>
                ))}
              </div>
            )}
            <div className="flex gap-2">
              <input
                className="input-glass flex-1"
                placeholder="Ajouter une information…"
                value={newInfo}
                onChange={e => setNewInfo(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && addExtraInfo()}
              />
              <button onClick={addExtraInfo} className="btn-glass px-4">+ Ajouter</button>
            </div>
          </div>

          <div className="flex justify-between">
            <button onClick={() => setStep(0)} className="btn-glass">← Retour</button>
            <button onClick={() => setStep(2)} className="btn-primary">
              Articles <ChevronRight size={16} />
            </button>
          </div>
        </div>
      )}

      {/* ── STEP 2 : Articles ── */}
      {step === 2 && (
        <div className="space-y-5 animate-fade-in">
          <div className="glass-card p-0 overflow-hidden">
            <div className="flex items-center justify-between px-4 py-3 border-b border-slate-200/50 dark:border-slate-700/30 flex-wrap gap-2">
              <h3 className="font-display font-bold text-base">Articles</h3>
              <div className="flex gap-2 flex-wrap">
                {availableItems.length > 0 && (
                  <button onClick={openItemsModal} className="btn-glass text-sm">
                    <Package size={14} /> Items existants
                  </button>
                )}
                {availableCols.length > 0 && (
                  <button onClick={openColsModal} className="btn-glass text-sm">
                    <List size={14} /> Colonnes existantes
                  </button>
                )}
                {showAddCol ? (
                  <div className="flex gap-1">
                    <input
                      autoFocus
                      className="input-glass text-sm py-1 px-2 w-36"
                      placeholder="Nom colonne"
                      value={newColName}
                      onChange={e => setNewColName(e.target.value)}
                      onKeyDown={e => { if (e.key === 'Enter') addColumn(); if (e.key === 'Escape') setShowAddCol(false); }}
                    />
                    <button onClick={addColumn} className="btn-glass text-xs px-2"><Check size={14} /></button>
                    <button onClick={() => setShowAddCol(false)} className="btn-glass text-xs px-2 text-red-400"><X size={14} /></button>
                  </div>
                ) : (
                  <button onClick={() => setShowAddCol(true)} className="btn-glass text-sm">
                    <Columns size={14} /> + Colonne
                  </button>
                )}
                <button onClick={addRow} className="btn-glass text-sm">
                  <Plus size={14} /> + Ligne
                </button>
              </div>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="bg-gradient-to-r from-blue-50/80 to-cyan-50/60 dark:from-blue-950/30 dark:to-cyan-950/20">
                    {tableColumns.map(col => (
                      <th key={col} className="px-4 py-3 text-left font-mono text-xs uppercase tracking-wider whitespace-nowrap" style={{ color: primary }}>
                        {col}
                        {col !== 'Description' && (
                          <button onClick={() => deleteColumn(col)} className="ml-2 text-slate-300 hover:text-red-400 transition-colors">
                            <X size={11} />
                          </button>
                        )}
                      </th>
                    ))}
                    <th className="px-3 py-3 w-10" />
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 dark:divide-slate-800/50">
                  {tableRows.length === 0 ? (
                    <tr>
                      <td colSpan={tableColumns.length + 1} className="text-center py-12 text-slate-400 italic text-sm">
                        Utilisez les boutons ci-dessus pour ajouter des items/colonnes,<br/>ou cliquez "+ Ligne" pour saisir manuellement
                      </td>
                    </tr>
                  ) : (
                    tableRows.map((row, rowIdx) => (
                      <tr key={rowIdx} className="hover:bg-blue-50/20 dark:hover:bg-slate-800/20 transition-colors group">
                        {tableColumns.map((col, colIdx) => {
                          const isEditing = editingCell?.r === rowIdx && editingCell?.c === col;
                          return (
                            <td key={col}
                              className={`px-4 py-2 ${colIdx === 0 ? 'font-medium text-slate-800 dark:text-slate-200' : 'font-mono text-right text-slate-600 dark:text-slate-400'}`}
                              onDoubleClick={() => setEditingCell({ r: rowIdx, c: col })}
                            >
                              {isEditing ? (
                                <input
                                  autoFocus
                                  className="w-full bg-transparent border-b-2 border-cyan-400 outline-none px-1 py-0.5 text-sm"
                                  defaultValue={row[col] || ''}
                                  onBlur={e => updateCell(rowIdx, col, e.target.value)}
                                  onKeyDown={e => {
                                    if (e.key === 'Enter') updateCell(rowIdx, col, e.target.value);
                                    if (e.key === 'Escape') setEditingCell(null);
                                    if (e.key === 'Tab') {
                                      e.preventDefault();
                                      updateCell(rowIdx, col, e.target.value);
                                      const next = tableColumns[colIdx + 1];
                                      if (next) setEditingCell({ r: rowIdx, c: next });
                                      else if (rowIdx < tableRows.length - 1) setEditingCell({ r: rowIdx + 1, c: tableColumns[0] });
                                    }
                                  }}
                                />
                              ) : (
                                <span className="block truncate max-w-[200px]" title={row[col]}>
                                  {row[col] || <span className="text-slate-300 dark:text-slate-600 text-xs">—</span>}
                                </span>
                              )}
                            </td>
                          );
                        })}
                        <td className="px-2 py-2 opacity-0 group-hover:opacity-100 transition-opacity">
                          <button onClick={() => deleteRow(rowIdx)} className="text-slate-300 hover:text-red-400 transition-colors">
                            <Trash2 size={14} />
                          </button>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
            <p className="text-right text-xs text-slate-400 px-4 py-2 border-t border-slate-100 dark:border-slate-800/30">
              Double-clic pour éditer · Tab pour naviguer
            </p>
          </div>

          <div className="flex justify-between">
            <button onClick={() => setStep(1)} className="btn-glass">← Retour</button>
            <button onClick={() => setStep(3)} className="btn-primary">
              Récapitulatif <ChevronRight size={16} />
            </button>
          </div>
        </div>
      )}

      {/* ── STEP 3 : Récapitulatif ── */}
      {step === 3 && (
        <div className="space-y-5 animate-fade-in">
          <div className="glass-card">
            <h3 className="font-display font-bold text-base mb-4 flex items-center gap-2">
              <FileText size={18} style={{ color: primary }} /> Récapitulatif
            </h3>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
              <div>
                <span className="text-xs text-slate-400 uppercase tracking-wider">Concession</span>
                <p className="font-medium text-slate-800 dark:text-slate-200 mt-1">
                  {concessionsList.find(c => String(c.id_concession) === String(selectedConcession))?.nom || '—'}
                </p>
              </div>
              <div>
                <span className="text-xs text-slate-400 uppercase tracking-wider">Fournisseur</span>
                <p className="font-medium text-slate-800 dark:text-slate-200 mt-1">{meta.fournisseur || '—'}</p>
              </div>
              <div>
                <span className="text-xs text-slate-400 uppercase tracking-wider">Date</span>
                <p className="font-medium text-slate-800 dark:text-slate-200 mt-1">
                  {meta.date ? new Date(meta.date).toLocaleDateString('fr-FR') : '—'}
                </p>
              </div>
              <div>
                <span className="text-xs text-slate-400 uppercase tracking-wider">Devise</span>
                <p className="font-medium text-slate-800 dark:text-slate-200 mt-1">{meta.devise || 'EUR'}</p>
              </div>
            </div>
            {extraInfos.length > 0 && (
              <div className="mt-4 pt-4 border-t border-slate-100 dark:border-slate-700/30">
                <span className="text-xs text-slate-400 uppercase tracking-wider">Infos complémentaires</span>
                <ul className="mt-1 space-y-1">
                  {extraInfos.map((info, i) => (
                    <li key={i} className="text-sm text-slate-700 dark:text-slate-300 flex items-center gap-1">
                      <span className="text-cyan-400">•</span> {info}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>

          <div className="glass-card p-0 overflow-hidden">
            <div className="px-4 py-3 border-b border-slate-100 dark:border-slate-800/30 flex items-center justify-between">
              <h3 className="font-display font-bold text-base">
                Articles <span className="text-slate-400 font-normal text-sm ml-1">
                  ({tableRows.filter(r => r[tableColumns[0]]?.trim()).length} lignes)
                </span>
              </h3>
              <button onClick={() => setStep(2)} className="text-xs text-cyan-500 hover:underline flex items-center gap-1">
                <Edit2 size={12} /> Modifier
              </button>
            </div>
            <div className="overflow-x-auto max-h-64">
              <table className="w-full text-sm">
                <thead className="sticky top-0 bg-slate-50 dark:bg-slate-800/60">
                  <tr>
                    {tableColumns.map(col => (
                      <th key={col} className="px-4 py-2 text-left font-mono text-xs uppercase tracking-wider text-slate-500">{col}</th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 dark:divide-slate-800/30">
                  {tableRows.filter(r => r[tableColumns[0]]?.trim()).map((row, i) => (
                    <tr key={i} className="hover:bg-slate-50 dark:hover:bg-slate-800/20">
                      {tableColumns.map((col, ci) => (
                        <td key={col} className={`px-4 py-2 ${ci === 0 ? 'font-medium text-slate-800 dark:text-slate-200' : 'font-mono text-right text-slate-500'}`}>
                          {row[col] || '—'}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="glass-card flex items-center justify-between gap-4 flex-wrap">
            <label className="flex items-center gap-2 text-sm cursor-pointer text-slate-600 dark:text-slate-300">
              <input
                type="checkbox"
                checked={forceOverwrite}
                onChange={e => setForceOverwrite(e.target.checked)}
                className="rounded accent-cyan-500"
              />
              Écraser si existante
            </label>
            <div className="flex gap-2">
              <button onClick={() => setStep(2)} className="btn-glass">← Retour</button>
              <button onClick={validateSemantic} className="btn-primary bg-gradient-to-r from-purple-500 to-blue-500">
                <Brain size={16} /> Valider sémantique
              </button>
              <button onClick={() => saveFacture()} className="btn-primary">
                <Save size={16} /> Enregistrer
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── MODAL ITEMS ── */}
      {showItemsModal && (
        <Modal
          title="Items existants"
          icon={<Package size={18} style={{ color: primary }} />}
          onClose={() => setShowItemsModal(false)}
          footer={
            <div className="flex gap-2">
              <button onClick={() => setShowItemsModal(false)} className="btn-glass flex-1">Annuler</button>
              <button onClick={confirmItems} className="btn-primary flex-1">
                Ajouter ({Object.values(checkedItems).filter(Boolean).length} sélectionné(s))
              </button>
            </div>
          }
        >
          <p className="text-xs text-slate-500 mb-3">Cochez les items à ajouter comme lignes :</p>
          <input
            className="input-glass w-full mb-3"
            placeholder="Rechercher…"
            value={itemSearch}
            onChange={e => setItemSearch(e.target.value)}
          />
          <div className="space-y-1">
            {filteredItems.length === 0 ? (
              <p className="text-center text-slate-400 py-6 italic text-sm">Aucun item trouvé</p>
            ) : (
              filteredItems.map((item, i) => (
                <label key={i} className={`flex items-center gap-3 p-2 rounded-lg cursor-pointer transition-colors ${checkedItems[item] ? 'bg-cyan-50 dark:bg-cyan-900/20' : 'hover:bg-slate-50 dark:hover:bg-slate-800/30'}`}>
                  <input
                    type="checkbox"
                    checked={!!checkedItems[item]}
                    onChange={() => setCheckedItems(prev => ({ ...prev, [item]: !prev[item] }))}
                    className="rounded accent-cyan-500"
                  />
                  <span className="text-sm text-slate-700 dark:text-slate-300">{item}</span>
                </label>
              ))
            )}
          </div>
        </Modal>
      )}

      {/* ── MODAL COLONNES ── */}
      {showColsModal && (
        <Modal
          title="Colonnes existantes"
          icon={<List size={18} style={{ color: primary }} />}
          onClose={() => setShowColsModal(false)}
          footer={
            <div className="flex gap-2">
              <button onClick={() => setShowColsModal(false)} className="btn-glass flex-1">Annuler</button>
              <button onClick={confirmCols} className="btn-primary flex-1">Appliquer</button>
            </div>
          }
        >
          <p className="text-xs text-slate-500 mb-3">Cochez les colonnes à inclure dans le tableau :</p>
          <input
            className="input-glass w-full mb-3"
            placeholder="Rechercher…"
            value={colSearch}
            onChange={e => setColSearch(e.target.value)}
          />
          <label className="flex items-center gap-3 p-2 rounded-lg bg-slate-50 dark:bg-slate-800/30 mb-1">
            <input type="checkbox" checked disabled className="rounded accent-cyan-500" />
            <span className="text-sm font-medium text-slate-700 dark:text-slate-300">Description</span>
            <span className="text-xs text-slate-400 ml-auto">(obligatoire)</span>
          </label>
          <div className="space-y-1">
            {filteredCols.filter(c => c !== 'Description').length === 0 ? (
              <p className="text-center text-slate-400 py-4 italic text-sm">Aucune colonne trouvée</p>
            ) : (
              filteredCols.filter(c => c !== 'Description').map((col, i) => (
                <label key={i} className={`flex items-center gap-3 p-2 rounded-lg cursor-pointer transition-colors ${checkedCols[col] ? 'bg-cyan-50 dark:bg-cyan-900/20' : 'hover:bg-slate-50 dark:hover:bg-slate-800/30'}`}>
                  <input
                    type="checkbox"
                    checked={!!checkedCols[col]}
                    onChange={() => setCheckedCols(prev => ({ ...prev, [col]: !prev[col] }))}
                    className="rounded accent-cyan-500"
                  />
                  <span className="text-sm text-slate-700 dark:text-slate-300">{col}</span>
                </label>
              ))
            )}
          </div>
        </Modal>
      )}
    </div>
  );
}