import { useState, useRef, useEffect } from 'react';
import { useApp } from '../context/AppContext';
import { apiCall } from '../api/api';
import axios from 'axios';
import { TabulatorFull as Tabulator } from 'tabulator-tables';
import 'tabulator-tables/dist/css/tabulator.min.css';
import ExtractionProgress from '../components/ExtractionProgress';
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

  const tableRef = useRef(null);
  const tabulatorRef = useRef(null);
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
      
      setShowProgress(false);
      
      const result = response.data;
      
      // 🔍 Debug
      console.log("=== RÉPONSE API ===");
      console.log("Colonnes reçues:", result.columns);
      console.log("Items reçus:", result.items?.length);
      if (result.items?.length > 0) {
        console.log("Premier item:", result.items[0]);
      }
      
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
    } catch (error) {
      console.error('Erreur extraction:', error);
      setShowProgress(false);
      showToast("Erreur lors de l'extraction", 'danger');
    }
  };

  const handleExtractionComplete = (result) => {
    console.log("=== handleExtractionComplete ===");
    console.log("Items:", result.items?.length);
    console.log("Colonnes:", result.columns);
    setExtraction(result);
    setShowProgress(false);
    setTaskId(null);
    showToast('Extraction réussie !', 'success');
  };

  const handleExtractionError = (message) => {
    setShowProgress(false);
    setTaskId(null);
    showToast(message || "Erreur d'extraction", 'danger');
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

  const handleSemanticValidation = async () => {
    if (!concessionId) {
      showToast('⚠️ Sélectionnez une Concession.', 'warning');
      return;
    }
    if (!tabulatorRef.current) return;

    showSpinner();
    try {
      const itemsData = tabulatorRef.current.getData().map(row => {
        const { description, ...valeurs } = row;
        const cleanedValeurs = {};
        Object.entries(valeurs).forEach(([k, v]) => {
          if (v !== undefined && v !== null && v !== '') cleanedValeurs[k] = cleanValue(v);
        });
        return { description: cleanValue(description || ''), valeurs: cleanedValeurs };
      });

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
            semantic: result
          });
        } catch {
          validationResults.push({ ...item, semantic: { needs_confirmation: false, auto_match: false } });
        }
      }

      const items = await apiCall('GET', '/items', null, { id_concession: concessionId });
      setExistingItems(items);
      setValidationItems(validationResults);
      setShowValidation(true);

      const needsValidation = validationResults.filter(v => v.semantic.needs_confirmation);
      const autoMatched = validationResults.filter(v => v.semantic.auto_match && !v.semantic.needs_confirmation);
      showToast(`${autoMatched.length} items matchés automatiquement, ${needsValidation.length} à valider`, 'info');
    } catch {
      showToast('Erreur lors de la validation sémantique', 'danger');
    } finally {
      hideSpinner();
    }
  };

  const saveFacture = async (decisions = {}) => {
    if (!concessionId) {
      showToast('⚠️ Sélectionnez une Concession.', 'warning');
      return;
    }
    if (!tabulatorRef.current) return;

    showSpinner();
    try {
      const itemsData = tabulatorRef.current.getData().map((row, idx) => {
        const { description, ...valeurs } = row;
        const cleanedValeurs = {};
        Object.entries(valeurs).forEach(([k, v]) => {
          if (v !== undefined && v !== null && v !== '') cleanedValeurs[k] = cleanValue(v);
        });
        
        const decision = decisions[idx] || { decision: 'new', targetItemId: null };
        return {
          description: cleanValue(description || ''),
          valeurs: cleanedValeurs,
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

  // ✅ Initialize Tabulator - VERSION CORRIGÉE
  useEffect(() => {
    if (!extraction?.items || !tableRef.current) return;

    if (tabulatorRef.current) {
      tabulatorRef.current.destroy();
      tabulatorRef.current = null;
    }

    const originalColumns = extraction.columns || [];
    const cleanedColumns = originalColumns.map(col => String(col).trim());
    
    console.log("=== INIT TABULATOR ===");
    console.log("Colonnes originales:", cleanedColumns);
    console.log("Items reçus:", extraction.items.length);
    
    // Construire les colonnes Tabulator
    const columns = [
      {
        title: extraction.metadata?.first_column_name || 'Description',
        field: 'description',
        editor: 'input',
        minWidth: 250,
        headerSort: false,
      },
    ];

    // Pour chaque colonne, créer une colonne Tabulator
    cleanedColumns.forEach((col) => {
      const safeField = col.replace(/[^a-zA-Z0-9\u00C0-\u024F]/g, '_');
      columns.push({
        title: col,
        field: safeField,
        editor: 'input',
        minWidth: 140,
        hozAlign: 'center',
      });
    });

    // Construire les données avec le bon mapping
    const tableData = extraction.items.map((item, idx) => {
      const row = { 
        id: idx, 
        description: cleanValue(item.description || item.libelle || '') 
      };
      
      // Initialiser toutes les colonnes à vide
      cleanedColumns.forEach(col => {
        const safeField = col.replace(/[^a-zA-Z0-9\u00C0-\u024F]/g, '_');
        row[safeField] = '';
      });
      
      // Remplir les valeurs
      const valeurs = item.valeurs || {};
      
      // Méthode 1: Chercher par correspondance exacte du titre
      Object.entries(valeurs).forEach(([key, value]) => {
        // Chercher la colonne dont le titre correspond à la clé
        const matchingCol = cleanedColumns.find(col => 
          col.toLowerCase() === key.toLowerCase()
        );
        
        if (matchingCol) {
          const safeField = matchingCol.replace(/[^a-zA-Z0-9\u00C0-\u024F]/g, '_');
          row[safeField] = cleanValue(value);
          console.log(`  Match exact: ${key} -> ${matchingCol} = ${value}`);
        } else {
          // Méthode 2: Chercher par similarité (suppression des caractères spéciaux)
          const normalizedKey = key.toLowerCase().replace(/[^a-z]/g, '');
          const matchingColFuzzy = cleanedColumns.find(col => {
            const normalizedCol = col.toLowerCase().replace(/[^a-z]/g, '');
            return normalizedCol === normalizedKey;
          });
          
          if (matchingColFuzzy) {
            const safeField = matchingColFuzzy.replace(/[^a-zA-Z0-9\u00C0-\u024F]/g, '_');
            row[safeField] = cleanValue(value);
            console.log(`  Match fuzzy: ${key} -> ${matchingColFuzzy} = ${value}`);
          } else {
            // Méthode 3: Utiliser directement la clé comme nom de champ
            const safeField = key.replace(/[^a-zA-Z0-9\u00C0-\u024F]/g, '_');
            // Vérifier si ce champ existe dans les colonnes
            const columnExists = columns.some(col => col.field === safeField);
            if (columnExists) {
              row[safeField] = cleanValue(value);
              console.log(`  Match direct: ${key} -> ${safeField} = ${value}`);
            } else {
              console.log(`  Aucun match pour: ${key}`);
            }
          }
        }
      });
      
      return row;
    });

    console.log("TableData construit:", tableData.length, "lignes");
    if (tableData.length > 0) {
      console.log("Première ligne:", tableData[0]);
    }

    setTimeout(() => {
      tabulatorRef.current = new Tabulator(tableRef.current, {
        data: tableData,
        columns,
        layout: 'fitDataFill',
        height: 'auto',
        maxHeight: '500px',
        editable: true,
        movableColumns: false,
        placeholder: 'Aucune donnée détectée',
      });
      
      console.log("Tabulator initialisé avec", columns.length, "colonnes");
    }, 100);
  }, [extraction]);

  // ==================== UPLOAD VIEW ====================
  if (showProgress && taskId && !extraction) {
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
        <div className="flex items-center gap-2 px-4 py-2 rounded-full glass border-emerald-200 dark:border-emerald-500/20">
          <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
          <span className="text-xs font-mono text-emerald-700 dark:text-emerald-400">OCR Validé</span>
        </div>
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
          <span className="font-display text-2xl font-bold">{extraction.items?.length || 0}</span>
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
            <input type="text" value={meta.fournisseur} onChange={(e) => setMeta(p => ({ ...p, fournisseur: e.target.value }))} className="input-glass" placeholder="Nom du fournisseur" />
          </div>
        </div>
      </div>

      <div className="glass-card p-4">
        <div className="flex justify-between items-center mb-4">
          <h3 className="font-display font-bold text-lg text-slate-800 dark:text-white">Articles extraits</h3>
          <div className="flex gap-2">
            <button className="btn-glass text-sm"><Columns size={16} /> Colonne</button>
            <button className="btn-glass text-sm"><Plus size={16} /> Ligne</button>
          </div>
        </div>
        <div className="overflow-x-auto rounded-xl border border-slate-200/30 dark:border-slate-700/30">
          <div ref={tableRef} />
        </div>
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
          <button onClick={saveFacture} className="btn-primary">
            <Save size={18} />
            Enregistrer
          </button>
        </div>
      </div>
    </div>
  );
}