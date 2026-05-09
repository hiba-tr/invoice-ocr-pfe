import { useState, useRef, useEffect } from 'react';
import { useApp } from '../context/AppContext';
import { apiCall } from '../api/api';
import axios from 'axios';
import { TabulatorFull as Tabulator } from 'tabulator-tables';
import 'tabulator-tables/dist/css/tabulator.min.css';
import {
  UploadCloud, Save, Plus, Columns,
  Sparkles, FileText, X
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
    showSpinner();
    try {
      const formData = new FormData();
      formData.append('file', files[0]);
      const resp = await axios.post(`${API_BASE}/upload`, formData);
      const inv = resp.data.invoices ? resp.data.invoices[0] : resp.data;
      setExtraction(inv);

      if (inv?.metadata) {
        setMeta({
          date: inv.metadata.date || '',
          fournisseur: inv.metadata.company || inv.metadata.fournisseur || '',
          currency: inv.metadata.currency || 'EUR',
          company: inv.metadata.company || '',
        });

        if (inv.metadata.concession) {
          try {
            const match = await apiCall('GET', '/match-concession', null, { nom_extrait: inv.metadata.concession });
            if (match.matched) setConcessionId(match.concession_id);
          } catch {
            // Silencieux : pas de match trouvé
          }
        }
      }
      showToast('Extraction réussie !', 'success');
    } catch {
      showToast("Erreur lors de l'extraction IA", 'danger');
    } finally {
      hideSpinner();
    }
  };

  const handleCreateConcession = async () => {
    if (!newConcessionName.trim()) return;
    try {
      const newC = await apiCall('POST', '/concessions', null, { nom: newConcessionName.trim() });
      setConcessionsList(prev => [...prev, newC]);
      setConcessionId(newC.id_concession);
      setNewConcessionName('');
      showToast('Concession créée', 'success');
    } catch {
      showToast('Erreur création concession', 'danger');
    }
  };

  const saveFacture = async () => {
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
    } catch {
      showToast('❌ Erreur lors de la sauvegarde.', 'danger');
    } finally {
      hideSpinner();
    }
  };

  // Initialize Tabulator when extraction changes
  // Initialize Tabulator when extraction changes
// Initialize Tabulator when extraction changes
useEffect(() => {
  if (!extraction?.items || !tableRef.current) return;

  if (tabulatorRef.current) {
    tabulatorRef.current.destroy();
    tabulatorRef.current = null;
  }

  const originalColumns = extraction.columns || [];
  const cleanedColumns = originalColumns.map(col => String(col).trim());
  const colMap = {};
  
  // Colonnes : AUCUNE colonne figée, tout défile ensemble
  const columns = [
    {
      title: extraction.metadata?.first_column_name || 'Description',
      field: 'description',
      editor: 'input',
      minWidth: 250,
      headerSort: false,
    },
  ];

  cleanedColumns.forEach(col => {
    const safeField = col.replace(/[^a-zA-Z0-9\u00C0-\u024F]/g, '_');
    colMap[col] = safeField;
    columns.push({
      title: col,
      field: safeField,
      editor: 'input',
      minWidth: 140,
      hozAlign: 'center',
    });
  });

  const tableData = extraction.items.map((item, idx) => {
    const row = { id: idx, description: cleanValue(item.description || item.libelle || '') };
    // Initialiser toutes les colonnes à vide
    columns.forEach(col => {
      if (col.field !== 'description' && col.field !== 'id') {
        row[col.field] = '';
      }
    });
    const valeurs = item.valeurs;
    if (valeurs && typeof valeurs === 'object' && !Array.isArray(valeurs)) {
      Object.entries(valeurs).forEach(([key, value]) => {
        const safeField = key.trim().replace(/[^a-zA-Z0-9\u00C0-\u024F]/g, '_');
        if (safeField && Object.prototype.hasOwnProperty.call(row, safeField)) {
          row[safeField] = cleanValue(value);
        }
      });
    }
    return row;
  });

  setTimeout(() => {
    tabulatorRef.current = new Tabulator(tableRef.current, {
      data: tableData,
      columns,
      layout: 'fitDataFill',    // S'adapte exactement à la largeur des données
      height: 'auto',            // Hauteur automatique selon le contenu
      maxHeight: '500px',        // Mais pas plus de 500px (scroll si plus)
      editable: true,
      movableColumns: false,
      placeholder: 'Aucune donnée détectée',
    });
  }, 100);
}, [extraction]);

  // ==================== UPLOAD VIEW ====================
  if (!extraction) {
    return (
      <div className="max-w-2xl mx-auto space-y-8 animate-fade-in">
        {/* Header */}
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

        {/* Upload Zone */}
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
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.png,.jpg,.jpeg"
            multiple
            className="hidden"
            onChange={(e) => handleFiles(e.target.files)}
          />
        </div>

        {/* File Queue */}
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

        {/* Extract Button */}
        <button onClick={handleExtract} disabled={!files.length} className="btn-primary w-full text-lg py-4">
          <Sparkles size={22} />
          Lancer l'extraction IA
        </button>
      </div>
    );
  }

  // ==================== RESULTS VIEW ====================
  return (
    <div className="max-w-7xl mx-auto space-y-6 animate-slide-up">
      {/* Success Header */}
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
          <span className="font-display text-2xl font-bold">{extraction.items?.length || 0}</span>
        </div>
        <div className="glass kpi-card accent-blue">
          <span className="text-2xl">💰</span>
          <span className="kpi-label">Montant total estimé</span>
          <span className="font-display text-xl font-bold text-primary-light dark:text-primary-dark">— €</span>
        </div>
      </div>

      {/* Metadata */}
      <div className="glass-card">
        <h3 className="font-display font-bold text-lg mb-4">Métadonnées</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-xs font-mono uppercase tracking-wider text-slate-500 mb-2">Concession</label>
            <div className="flex gap-2">
              <select
                value={concessionId}
                onChange={(e) => setConcessionId(e.target.value)}
                className="select-glass input-glass flex-1"
              >
                <option value="">-- Choisir --</option>
                {concessionsList.map(c => (
                  <option key={c.id_concession} value={c.id_concession}>{c.nom}</option>
                ))}
              </select>
              <input
                type="text"
                placeholder="Nouveau..."
                value={newConcessionName}
                onChange={(e) => setNewConcessionName(e.target.value)}
                className="input-glass w-32"
              />
              <button onClick={handleCreateConcession} className="btn-glass">Créer</button>
            </div>
          </div>
          <div>
            <label className="block text-xs font-mono uppercase tracking-wider text-slate-500 mb-2">Date</label>
            <input
              type="date"
              value={meta.date}
              onChange={(e) => setMeta(p => ({ ...p, date: e.target.value }))}
              className="input-glass"
            />
          </div>
          <div>
            <label className="block text-xs font-mono uppercase tracking-wider text-slate-500 mb-2">Devise</label>
            <input
              type="text"
              value={meta.currency}
              onChange={(e) => setMeta(p => ({ ...p, currency: e.target.value }))}
              className="input-glass"
            />
          </div>
          <div>
            <label className="block text-xs font-mono uppercase tracking-wider text-slate-500 mb-2">Fournisseur</label>
            <input
              type="text"
              value={meta.fournisseur}
              onChange={(e) => setMeta(p => ({ ...p, fournisseur: e.target.value }))}
              className="input-glass"
              placeholder="Nom du fournisseur"
            />
          </div>
        </div>
      </div>

      {/* Items Table */}
      <div className="glass-card p-4">
        <div className="flex justify-between items-center mb-4">
          <h3 className="font-display font-bold text-lg text-slate-800 dark:text-white">Articles extraits</h3>
          <div className="flex gap-2">
            <button className="btn-glass text-sm">
              <Columns size={16} /> Colonne
            </button>
            <button className="btn-glass text-sm">
              <Plus size={16} /> Ligne
            </button>
          </div>
        </div>
        {/* Conteneur avec overflow pour défilement horizontal */}
        <div className="overflow-x-auto rounded-xl border border-slate-200/30 dark:border-slate-700/30">
          <div ref={tableRef} />
        </div>
      </div>

      {/* Save Section */}
      <div className="glass-card flex flex-col sm:flex-row justify-between items-center gap-4">
        <label className="flex items-center gap-2 text-sm cursor-pointer">
          <input
            type="checkbox"
            checked={forceOverwrite}
            onChange={(e) => setForceOverwrite(e.target.checked)}
            className="rounded border-slate-300"
          />
          Écraser si existante
        </label>
        <button onClick={saveFacture} className="btn-primary">
          <Save size={18} />
          Enregistrer dans la base
        </button>
      </div>
    </div>
  );
}