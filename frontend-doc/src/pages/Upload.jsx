import { useState, useRef, useEffect } from 'react';
import { useApp } from '../context/AppContext';
import { apiCall } from '../api/api';
import axios from 'axios';
import ExtractionProgress from '../components/ExtractionProgress';
import SemanticValidation from '../components/SemanticValidation';
import {
  UploadCloud, Save, Plus, Columns,
  Sparkles, FileText, X, Brain, Trash2
} from 'lucide-react';

const API_BASE = 'http://localhost:8000';
const primaryColor = '#06b6d4';

const cleanValue = (val) => {
  if (val === null || val === undefined) return '';
  if (typeof val === 'number') return String(val);
  return String(val).replace(/\s+/g, ' ').trim();
};

export default function Upload() {
  const { showSpinner, hideSpinner, showToast, concessionsList, setConcessionsList } = useApp();

  const [files, setFiles] = useState([]);
  const [extraction, setExtraction] = useState(null);
  const [concessionId, setConcessionId] = useState('');
  const [newConcessionName, setNewConcessionName] = useState('');
  const [meta, setMeta] = useState({ date: '', fournisseur: '', currency: 'EUR', company: '' });
  const [forceOverwrite, setForceOverwrite] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const [taskId, setTaskId] = useState(null);
  const [showProgress, setShowProgress] = useState(false);
  const [showValidation, setShowValidation] = useState(false);
  const [validationItems, setValidationItems] = useState([]);
  const [existingItems, setExistingItems] = useState([]);

  // État du tableau natif (remplace Tabulator)
  const [tableColumns, setTableColumns] = useState([]); // ['Description', 'Col1', ...]
  const [tableRows, setTableRows] = useState([]);       // [{ description, col1, ... }, ...]
  const [editingCell, setEditingCell] = useState(null); // { rowIdx, col }

  const fileInputRef = useRef(null);

  useEffect(() => {
    apiCall('GET', '/concessions')
      .then(setConcessionsList)
      .catch(() => {});
  }, [setConcessionsList]);

  const handleFiles = (newFiles) => {
    setFiles(prev => [...prev, ...Array.from(newFiles)]);
  };

  const removeFile = (index) => {
    setFiles(prev => prev.filter((_, i) => i !== index));
  };

  const handleExtract = async () => {
    if (!files.length) {
      showToast("Veuillez d'abord choisir un fichier !", 'warning');
      return;
    }

    setShowProgress(true);
    const formData = new FormData();
    formData.append('file', files[0]);

    try {
      const response = await axios.post(`${API_BASE}/upload`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });

      const result = response.data;
      window.dispatchEvent(new CustomEvent('extraction-complete', { detail: { success: true, result } }));

      setTimeout(() => {
        setShowProgress(false);
        if (result.invoices) {
          handleExtractionComplete({
            items: result.invoices[0]?.items || [],
            columns: result.invoices[0]?.columns || [],
            metadata: result.invoices[0]?.metadata || {}
          });
        } else {
          handleExtractionComplete({
            items: result.items || [],
            columns: result.columns || [],
            metadata: result.metadata || {}
          });
        }
      }, 500);
    } catch (error) {
      console.error('Erreur extraction:', error);
      setShowProgress(false);
      showToast("Erreur lors de l'extraction", 'danger');
    }
  };

  const handleExtractionComplete = (result) => {
    setExtraction(result);
    setShowProgress(false);
    setTaskId(null);
    buildNativeTable(result);
    showToast('Extraction réussie !', 'success');
  };

  const handleExtractionError = (message) => {
    setShowProgress(false);
    setTaskId(null);
    showToast(message || "Erreur d'extraction", 'danger');
  };

  // Construit le tableau natif à partir du résultat d'extraction
  const buildNativeTable = (result) => {
    const originalColumns = result.columns || [];
    const seen = new Set();
    const cleanedColumns = originalColumns
      .map(col => String(col).trim())
      .filter(col => {
        const norm = col.toLowerCase().replace(/[^a-z]/g, '');
        if (seen.has(norm)) return false;
        seen.add(norm);
        return true;
      });

    const descLabel = result.metadata?.first_column_name || 'Description';
    const allColumns = [descLabel, ...cleanedColumns];

    const rows = (result.items || []).map((item) => {
      const row = { [descLabel]: cleanValue(item.description || item.libelle || '') };
      cleanedColumns.forEach(col => { row[col] = ''; });

      const valeurs = item.valeurs || {};
      Object.entries(valeurs).forEach(([key, value]) => {
        const match = cleanedColumns.find(col => col.toLowerCase() === key.toLowerCase())
          || cleanedColumns.find(col =>
            col.toLowerCase().replace(/[^a-z]/g, '') === key.toLowerCase().replace(/[^a-z]/g, '')
          );
        if (match) row[match] = cleanValue(value);
      });

      return row;
    });

    setTableColumns(allColumns);
    setTableRows(rows);
  };

  // Edition inline d'une cellule
  const handleCellEdit = (rowIdx, col, value) => {
    setTableRows(prev => prev.map((row, i) =>
      i === rowIdx ? { ...row, [col]: value } : row
    ));
  };

  // Ajouter une ligne vide
  const handleAddRow = () => {
    const emptyRow = {};
    tableColumns.forEach(col => { emptyRow[col] = ''; });
    setTableRows(prev => [...prev, emptyRow]);
  };

  // Supprimer une ligne
  const handleDeleteRow = (rowIdx) => {
    setTableRows(prev => prev.filter((_, i) => i !== rowIdx));
  };

  // Ajouter une colonne
  const handleAddColumn = () => {
    const name = prompt('Nom de la nouvelle colonne :');
    if (!name || tableColumns.includes(name)) return;
    setTableColumns(prev => [...prev, name]);
    setTableRows(prev => prev.map(row => ({ ...row, [name]: '' })));
  };

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

  // Retourne les données du tableau dans le même format qu'attendu par saveFacture/handleSemanticValidation
  const getTableData = () => {
    const [descCol, ...valueCols] = tableColumns;
    return tableRows.map(row => {
      const valeurs = {};
      valueCols.forEach(col => {
        if (row[col] !== undefined && row[col] !== '') valeurs[col] = cleanValue(row[col]);
      });
      return { description: cleanValue(row[descCol] || ''), valeurs };
    });
  };

  const handleSemanticValidation = async () => {
    if (!concessionId) { showToast('⚠️ Sélectionnez une Concession.', 'warning'); return; }

    showSpinner();
    try {
      const itemsData = getTableData();
      const validationResults = [];

      for (const item of itemsData) {
        if (!item.description) continue;
        try {
          const result = await apiCall('GET', '/suggest/confirm', null, {
            description: item.description,
            id_concession: concessionId
          });
          validationResults.push({ ...item, semantic: result });
        } catch {
          validationResults.push({ ...item, semantic: { needs_confirmation: false, auto_match: false } });
        }
      }

      const items = await apiCall('GET', '/items', null, { id_concession: concessionId });
      setExistingItems(items);
      setValidationItems(validationResults);
      setShowValidation(true);

      const autoMatched = validationResults.filter(v => v.semantic.auto_match && !v.semantic.needs_confirmation);
      const needsValidation = validationResults.filter(v => v.semantic.needs_confirmation);
      showToast(`${autoMatched.length} items matchés automatiquement, ${needsValidation.length} à valider`, 'info');
    } catch {
      showToast('Erreur lors de la validation sémantique', 'danger');
    } finally {
      hideSpinner();
    }
  };

  const saveFacture = async (decisions = {}) => {
    if (!concessionId) { showToast('⚠️ Sélectionnez une Concession.', 'warning'); return; }

    showSpinner();
    try {
      const itemsData = getTableData().map((item, idx) => {
        const decision = decisions[idx] || { decision: 'new', targetItemId: null };
        return {
          ...item,
          semantic_decision: decision.decision,
          semantic_target_id: decision.targetItemId,
          semantic_auto: decision.preselected ? '1' : '0',
        };
      });

      const payload = {
        facture: {
          fichier_source: files[0]?.name || 'Saisie Manuelle',
          date_facture: meta.date || null,
          devise: meta.currency || 'EUR',
          id_concession: parseInt(concessionId),
          total_montant: 0
        },
        items_data: itemsData
      };

      await apiCall('POST', '/facture', payload, { force: forceOverwrite });
      showToast('✅ Facture enregistrée avec succès !', 'success');
      setExtraction(null);
      setFiles([]);
      setTableColumns([]);
      setTableRows([]);
      setShowValidation(false);
    } catch (err) {
      if (err?.response?.status === 409) {
        showToast('Cette facture existe déjà. Cochez "Écraser si existe".', 'warning');
      } else {
        showToast('❌ Erreur lors de la sauvegarde.', 'danger');
      }
    } finally {
      hideSpinner();
    }
  };

  // ==================== UPLOAD VIEW ====================
  if (showProgress && !extraction) {
    return (
      <div className="max-w-2xl mx-auto">
        <ExtractionProgress
          taskId={taskId}
          onComplete={handleExtractionComplete}
          onError={handleExtractionError}
        />
      </div>
    );
  }

  if (!extraction) {
    return (
      <div className="max-w-2xl mx-auto space-y-8 animate-fade-in">
        <div className="text-center space-y-2">
          <div className="inline-flex items-center gap-2 text-xs font-mono uppercase tracking-widest" style={{ color: primaryColor }}>
            <span className="w-6 h-px" style={{ background: primaryColor }} />
            Import intelligent
          </div>
          <h1 className="font-display text-3xl font-extrabold text-slate-800 dark:text-white">
            Déposer une <span style={{ color: primaryColor }}>facture</span>
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
          <UploadCloud size={48} className="mx-auto mb-4" style={{ color: primaryColor }} />
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
                <FileText size={18} style={{ color: primaryColor }} />
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

  // ==================== VALIDATION VIEW ====================
  if (showValidation) {
    return (
      <div className="max-w-7xl mx-auto space-y-6 animate-slide-up">
        <SemanticValidation
          items={validationItems}
          existingItems={existingItems}
          concessionId={concessionId}
          onSave={saveFacture}
          onBack={() => setShowValidation(false)}
          forceOverwrite={forceOverwrite}
          onForceOverwriteChange={setForceOverwrite}
        />
      </div>
    );
  }

  // ==================== RESULTS VIEW ====================
  return (
    <div className="max-w-7xl mx-auto space-y-6 animate-slide-up">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2 text-xs font-mono uppercase tracking-wider text-emerald-600 dark:text-emerald-400">
            <span className="w-6 h-px bg-emerald-500" />
            Résultat
          </div>
          <h2 className="font-display text-2xl font-extrabold text-slate-800 dark:text-white">
            Extraction <span style={{ color: primaryColor }}>terminée</span>
          </h2>
        </div>
        <div className="flex items-center gap-2 px-4 py-2 rounded-full glass border-emerald-200 dark:border-emerald-500/20">
          <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
          <span className="text-xs font-mono text-emerald-700 dark:text-emerald-400">OCR Validé</span>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="glass kpi-card accent-cyan">
          <span className="text-2xl">📄</span>
          <span className="kpi-label">Fichier traité</span>
          <span className="font-display text-lg font-bold truncate">{files[0]?.name || '—'}</span>
        </div>
        <div className="glass kpi-card accent-green">
          <span className="text-2xl">✅</span>
          <span className="kpi-label">Articles extraits</span>
          <span className="font-display text-2xl font-bold">{tableRows.length}</span>
        </div>
        <div className="glass kpi-card accent-blue">
          <span className="text-2xl">💰</span>
          <span className="kpi-label">Montant total estimé</span>
          <span className="font-display text-xl font-bold" style={{ color: primaryColor }}>— €</span>
        </div>
      </div>

      {/* Métadonnées */}
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
            <input type="text" value={meta.fournisseur} onChange={(e) => setMeta(p => ({ ...p, fournisseur: e.target.value }))} className="input-glass" placeholder="Nom du fournisseur" />
          </div>
        </div>
      </div>

      {/* Tableau des articles — même style que History.jsx */}
      <div className="glass-card p-4">
        <div className="flex justify-between items-center mb-4">
          <h3 className="font-display font-bold text-lg text-slate-800 dark:text-white">
            Articles extraits
          </h3>
          <div className="flex gap-2">
            <button onClick={handleAddColumn} className="btn-glass text-sm">
              <Columns size={16} /> Colonne
            </button>
            <button onClick={handleAddRow} className="btn-glass text-sm">
              <Plus size={16} /> Ligne
            </button>
          </div>
        </div>

        <div className="overflow-x-auto rounded-xl border border-slate-200/30 dark:border-slate-700/30">
          {tableRows.length === 0 ? (
            <p className="text-center text-slate-400 dark:text-slate-500 py-10 italic">
              Aucune donnée détectée
            </p>
          ) : (
            <table className="w-full text-sm" style={{ minWidth: '100%' }}>
              <thead>
                <tr className="bg-gradient-to-r from-blue-50/80 to-cyan-50/80 dark:from-blue-950/30 dark:to-cyan-950/20">
                  {tableColumns.map((col) => (
                    <th
                      key={col}
                      className="px-4 py-3 text-left font-mono text-xs uppercase tracking-wider whitespace-nowrap"
                      style={{ color: primaryColor }}
                    >
                      {col}
                    </th>
                  ))}
                  {/* Colonne action suppression */}
                  <th className="px-4 py-3 w-10" />
                </tr>
              </thead>
              <tbody className="divide-y divide-blue-100/50 dark:divide-slate-800/50">
                {tableRows.map((row, rowIdx) => (
                  <tr
                    key={rowIdx}
                    className="hover:bg-blue-50/30 dark:hover:bg-slate-800/30 transition-colors"
                  >
                    {tableColumns.map((col, colIdx) => {
                      const isEditing = editingCell?.rowIdx === rowIdx && editingCell?.col === col;
                      const isFirst = colIdx === 0;
                      return (
                        <td
                          key={col}
                          className={`px-4 py-2 whitespace-nowrap ${
                            isFirst
                              ? 'font-medium text-slate-800 dark:text-slate-200'
                              : 'font-mono text-right text-slate-600 dark:text-slate-400'
                          }`}
                          onClick={() => setEditingCell({ rowIdx, col })}
                        >
                          {isEditing ? (
                            <input
                              autoFocus
                              className="w-full bg-transparent outline-none border-b border-cyan-400 dark:border-cyan-500 text-slate-800 dark:text-slate-100 text-sm"
                              value={row[col] ?? ''}
                              onChange={(e) => handleCellEdit(rowIdx, col, e.target.value)}
                              onBlur={() => setEditingCell(null)}
                              onKeyDown={(e) => { if (e.key === 'Enter' || e.key === 'Escape') setEditingCell(null); }}
                            />
                          ) : (
                            <span className="cursor-text">{row[col] || '—'}</span>
                          )}
                        </td>
                      );
                    })}
                    <td className="px-2 py-2 text-center">
                      <button
                        onClick={() => handleDeleteRow(rowIdx)}
                        className="p-1 text-slate-300 hover:text-red-500 dark:text-slate-600 dark:hover:text-red-400 transition-colors"
                      >
                        <Trash2 size={14} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        <p className="text-right text-xs font-mono text-slate-400 dark:text-slate-500 mt-2">
          Cliquez sur une cellule pour l'éditer
        </p>
      </div>

      {/* Footer actions */}
      <div className="glass-card flex flex-col sm:flex-row justify-between items-center gap-4">
        <label className="flex items-center gap-2 text-sm cursor-pointer select-none">
          <input
            type="checkbox"
            checked={forceOverwrite}
            onChange={(e) => setForceOverwrite(e.target.checked)}
            className="rounded border-slate-300 accent-cyan-500"
          />
          Écraser si existante
        </label>
        <div className="flex gap-2">
          <button onClick={handleSemanticValidation} className="btn-primary" style={{ background: 'linear-gradient(135deg, #7c3aed, #4361ee)' }}>
            <Brain size={18} />
            Validation sémantique
          </button>
          <button onClick={() => saveFacture()} className="btn-primary">
            <Save size={18} />
            Enregistrer
          </button>
        </div>
      </div>
    </div>
  );
}