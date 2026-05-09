import { useState, useEffect, useRef } from 'react';
import { useApp } from '../context/AppContext';
import { apiCall } from '../api/api';
import { TabulatorFull as Tabulator } from 'tabulator-tables';
import 'tabulator-tables/dist/css/tabulator.min.css';
import { PenTool, Plus, Save, Building2, List } from 'lucide-react';

export default function Manual() {
  const { showSpinner, hideSpinner, showToast, concessionsList, setConcessionsList } = useApp();
  const [selectedConcession, setSelectedConcession] = useState('');
  const [newConcessionName, setNewConcessionName] = useState('');
  const [meta, setMeta] = useState({ date: '', devise: 'EUR', numero: '' });
  const [forceOverwrite, setForceOverwrite] = useState(false);
  const [showItemsModal, setShowItemsModal] = useState(false);
  const [showColsModal, setShowColsModal] = useState(false);
  const [availableItems, setAvailableItems] = useState([]);
  const [availableCols, setAvailableCols] = useState([]);
  const [selectedItems, setSelectedItems] = useState([]);
  const [formReady, setFormReady] = useState(false);

  const tableRef = useRef(null);
  const tabulatorRef = useRef(null);

  useEffect(() => {
    apiCall('GET', '/concessions')
      .then(setConcessionsList)
      .catch(() => {});
  }, [setConcessionsList]);

  const selectConcession = async (id) => {
    setSelectedConcession(id);
    setFormReady(false);
    if (!id) return;

    showSpinner();
    try {
      const items = await apiCall('GET', '/items', null, { id_concession: id });
      const itemLabels = items.map(it => it.libelle_canonique).filter(Boolean);
      setAvailableItems(itemLabels);
      if (itemLabels.length > 0) {
        setShowItemsModal(true);
      } else {
        promptCols([]);
      }
    } catch {
      showToast('Erreur chargement items', 'danger');
    } finally {
      hideSpinner();
    }
  };

  const promptCols = async (descriptions) => {
    setSelectedItems(descriptions);
    setShowItemsModal(false);
    showSpinner();
    try {
      const colonnes = await apiCall('GET', '/colonnes', null, { id_concession: selectedConcession });
      const colLabels = colonnes.map(c => c.libelle_canonique);
      if (colLabels.length === 0) {
        finalizeTable(['Description', 'Montant'], descriptions);
      } else {
        setAvailableCols(colLabels.includes('Description') ? colLabels : ['Description', ...colLabels]);
        setShowColsModal(true);
      }
    } catch {
      showToast('Erreur chargement colonnes', 'danger');
    } finally {
      hideSpinner();
    }
  };

  const finalizeTable = (cols, descriptions) => {
    setShowColsModal(false);
    setFormReady(true);

    const colDefs = [
      { title: 'Description', field: 'description', editor: 'input', width: 300, frozen: true },
      ...cols.filter(c => c !== 'Description').map(c => ({ title: c, field: c, editor: 'input' })),
    ];

    const rows = descriptions.length > 0
      ? descriptions.map(d => ({ description: d }))
      : [{ description: '' }];

    setTimeout(() => {
      if (tabulatorRef.current) tabulatorRef.current.destroy();
      tabulatorRef.current = new Tabulator(tableRef.current, {
        data: rows,
        columns: colDefs,
        layout: 'fitColumns',
        height: 350,
        editable: true,
        addRowPos: 'bottom',
      });
    }, 100);
  };

  const handleCreateConcession = async () => {
    if (!newConcessionName.trim()) return;
    showSpinner();
    try {
      const newC = await apiCall('POST', '/concessions', null, { nom: newConcessionName.trim() });
      setConcessionsList(prev => [...prev, newC]);
      setSelectedConcession(newC.id_concession);
      setNewConcessionName('');
      showToast('Concession créée', 'success');
    } catch {
      showToast('Erreur création', 'danger');
    } finally {
      hideSpinner();
    }
  };

  const saveFacture = async () => {
    if (!selectedConcession) return;
    if (!tabulatorRef.current) return;

    const tableData = tabulatorRef.current.getData();
    if (!tableData.length) {
      showToast('Ajoutez au moins un article', 'warning');
      return;
    }

    showSpinner();
    try {
      const itemsData = tableData.map(row => {
        const { description, ...valeurs } = row;
        const cleaned = {};
        Object.entries(valeurs).forEach(([k, v]) => {
          if (v !== undefined && v !== null && v !== '') cleaned[k] = String(v);
        });
        return { description: description || '', valeurs: cleaned };
      });

      await apiCall('POST', '/facture', {
        facture: {
          fichier_source: 'saisie_manuelle',
          date_facture: meta.date || null,
          devise: meta.devise,
          id_concession: parseInt(selectedConcession),
          numero_facture: meta.numero || null,
          total_montant: 0,
        },
        items_data: itemsData,
      }, { force: forceOverwrite });

      showToast('Facture enregistrée', 'success');
      setFormReady(false);
      setSelectedItems([]);
    } catch (err) {
      if (err?.response?.status === 409) {
        showToast('Facture existante. Cochez "Écraser si existe".', 'warning');
      } else {
        showToast('Erreur enregistrement', 'danger');
      }
    } finally {
      hideSpinner();
    }
  };

  return (
    <div className="max-w-6xl mx-auto space-y-6 animate-fade-in">
      <h1 className="font-display text-3xl font-extrabold text-slate-800 dark:text-white flex items-center gap-3">
        <PenTool className="text-primary-light dark:text-primary-dark" />
        Saisie manuelle
      </h1>

      {/* Step 1: Concession */}
      <div className="glass-card">
        <h3 className="font-display font-bold text-lg mb-4 flex items-center gap-2">
          <Building2 size={20} className="text-primary-light dark:text-primary-dark" />
          Concession
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 items-end">
          <select
            value={selectedConcession}
            onChange={(e) => selectConcession(e.target.value)}
            className="select-glass input-glass"
          >
            <option value="">-- Choisir --</option>
            {concessionsList.map(c => (
              <option key={c.id_concession} value={c.id_concession}>{c.nom}</option>
            ))}
          </select>
          <div className="flex gap-2">
            <input
              type="text"
              placeholder="Nouvelle concession"
              value={newConcessionName}
              onChange={(e) => setNewConcessionName(e.target.value)}
              className="input-glass flex-1"
              onKeyDown={(e) => e.key === 'Enter' && handleCreateConcession()}
            />
            <button onClick={handleCreateConcession} className="btn-glass">Créer</button>
          </div>
        </div>
      </div>

      {/* Step 2: Metadata */}
      {formReady && (
        <div className="glass-card animate-slide-up">
          <h3 className="font-display font-bold text-lg mb-4">Métadonnées</h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <input type="date" value={meta.date} onChange={(e) => setMeta(p => ({ ...p, date: e.target.value }))} className="input-glass" placeholder="Date" />
            <input type="text" value={meta.devise} onChange={(e) => setMeta(p => ({ ...p, devise: e.target.value }))} className="input-glass" placeholder="Devise" />
            <input type="text" value={meta.numero} onChange={(e) => setMeta(p => ({ ...p, numero: e.target.value }))} className="input-glass" placeholder="Numéro" />
          </div>
        </div>
      )}

        {/* Step 3: Articles Table */}
        {formReady && (
        <div className="glass-card animate-slide-up p-4">
            <div className="flex justify-between items-center mb-4">
            <h3 className="font-display font-bold text-lg text-slate-800 dark:text-white">Articles</h3>
            <div className="flex gap-2">
                <button onClick={() => setShowItemsModal(true)} className="btn-glass text-sm">
                <List size={16} /> Items existants
                </button>
                <button onClick={() => tabulatorRef.current?.addRow({ description: '' }, true)} className="btn-glass text-sm">
                <Plus size={16} /> Ligne
                </button>
            </div>
            </div>

            {/* Conteneur du tableau avec overflow et bordure style historique */}
            <div className="overflow-x-auto rounded-xl border border-slate-200/30 dark:border-slate-700/30">
            <div ref={tableRef} className="min-h-[300px]" />
            </div>

            <div className="flex items-center justify-between mt-6 pt-6 border-t border-slate-200/50 dark:border-slate-700/30">
            <label className="flex items-center gap-2 text-sm cursor-pointer text-slate-600 dark:text-slate-300">
                <input
                type="checkbox"
                checked={forceOverwrite}
                onChange={(e) => setForceOverwrite(e.target.checked)}
                className="rounded border-slate-300 dark:border-slate-600 text-primary-light focus:ring-primary-light/20"
                />
                Écraser si existe
            </label>
            <button onClick={saveFacture} className="btn-primary">
                <Save size={18} />
                Enregistrer la facture
            </button>
            </div>
        </div>
        )}

      {/* Items Modal */}
      {showItemsModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm" onClick={() => setShowItemsModal(false)}>
          <div className="glass-card w-96 max-h-[80vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
            <h3 className="font-bold mb-4">Items existants</h3>
            <div className="space-y-2">
              {availableItems.map((item, i) => (
                <label key={i} className="flex items-center gap-3 p-3 hover:bg-slate-50 dark:hover:bg-slate-800/30 rounded-lg cursor-pointer transition-colors">
                  <input type="checkbox" value={item} className="rounded" id={`item-${i}`} />
                  <span className="text-sm">{item}</span>
                </label>
              ))}
            </div>
            <button
              onClick={() => {
                const checked = Array.from(document.querySelectorAll('input[id^="item-"]:checked')).map(cb => cb.value);
                promptCols(checked);
              }}
              className="btn-primary w-full mt-6"
            >
              Étape suivante
            </button>
          </div>
        </div>
      )}

      {/* Columns Modal */}
      {showColsModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm" onClick={() => setShowColsModal(false)}>
          <div className="glass-card w-96" onClick={e => e.stopPropagation()}>
            <h3 className="font-bold mb-4">Colonnes à afficher</h3>
            <div className="space-y-2">
              {availableCols.map((col, i) => (
                <label key={i} className={`flex items-center gap-3 p-2 ${col === 'Description' ? 'opacity-50' : ''}`}>
                  <input
                    type="checkbox"
                    value={col}
                    defaultChecked
                    disabled={col === 'Description'}
                    className="rounded"
                    id={`col-${i}`}
                  />
                  <span className="text-sm">{col}</span>
                  {col === 'Description' && <span className="text-xs text-slate-400">(obligatoire)</span>}
                </label>
              ))}
            </div>
            <button
              onClick={() => {
                const checked = Array.from(document.querySelectorAll('input[id^="col-"]:checked')).map(cb => cb.value);
                finalizeTable(checked, selectedItems);
              }}
              className="btn-primary w-full mt-6"
            >
              Terminer
            </button>
          </div>
        </div>
      )}
    </div>
  );
}