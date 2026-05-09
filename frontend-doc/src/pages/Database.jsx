import { useState, useEffect, useRef } from 'react';
import { useApp } from '../context/AppContext';
import { apiCall } from '../api/api';
import { TabulatorFull as Tabulator } from 'tabulator-tables';
import 'tabulator-tables/dist/css/tabulator.min.css';
import { Trash2, Plus, Tag, ColumnsIcon, FileText } from 'lucide-react';

const TABS = [
  { id: 'items', label: 'Items', icon: Tag },
  { id: 'columns', label: 'Colonnes', icon: ColumnsIcon },
  { id: 'invoices', label: 'Factures', icon: FileText },
  { id: 'concessions', label: 'Concessions', icon: FileText },
];

export default function Database() {
  const { showSpinner, hideSpinner, showToast, concessionsList } = useApp();
  const [activeTab, setActiveTab] = useState('items');
  const [data, setData] = useState([]);
  const [search, setSearch] = useState('');
  const tableRef = useRef(null);
  const tabulatorRef = useRef(null);

  useEffect(() => {
    const fetchData = async () => {
      showSpinner();
      try {
        const endpoints = {
          items: '/items',
          columns: '/colonnes',
          invoices: '/factures',
          concessions: '/concessions',
        };
        const result = await apiCall('GET', endpoints[activeTab]);
        setData(result);
        setSearch('');
      } catch {
        showToast('Erreur chargement données', 'danger');
      } finally {
        hideSpinner();
      }
    };
    fetchData();
  }, [activeTab, hideSpinner, showSpinner, showToast]);

  // Initialize Tabulator
  useEffect(() => {
    if (!data.length || !tableRef.current) return;

    if (tabulatorRef.current) {
      tabulatorRef.current.destroy();
      tabulatorRef.current = null;
    }

    let columns = [];
    let tabulatorData = [];

    switch (activeTab) {
      case 'items':
        columns = [
          { title: 'ID', field: 'id_item', width: 80, frozen: true },
          { title: 'Libellé Canonique', field: 'libelle_canonique', editor: 'input', headerFilter: true },
          { title: 'Concession', field: 'id_concession', width: 120, hozAlign: 'center' },
          { title: 'Utilisations', field: 'usage_count', width: 120, hozAlign: 'center',
            formatter: (cell) => {
              const v = cell.getValue();
              return v > 0 ? `<span class="badge-status badge-success">${v} facture(s)</span>` : '<span class="text-slate-400">—</span>';
            }
          },
        ];
        tabulatorData = data;
        break;

      case 'columns':
        columns = [
          { title: 'ID', field: 'id_colonne', width: 80 },
          { title: 'Libellé', field: 'libelle_canonique', editor: 'input', headerFilter: true },
          { title: 'Concession', field: 'id_concession', width: 120, hozAlign: 'center' },
          { title: 'Utilisations', field: 'usage_count', width: 120, hozAlign: 'center',
            formatter: 'tickCross',
          },
        ];
        tabulatorData = data;
        break;

      case 'invoices':
        columns = [
          { title: 'ID', field: 'id_facture', width: 80 },
          { title: 'Date', field: 'date_facture', formatter: (cell) => cell.getValue()?.split('T')[0] || '—' },
          { title: 'Concession', field: 'id_concession' },
          { title: 'Fichier', field: 'fichier_source' },
          { title: 'Montant', field: 'total_montant', hozAlign: 'right',
            formatter: (cell) => `${(cell.getValue() || 0).toFixed(2)} €`
          },
        ];
        tabulatorData = data;
        break;

      case 'concessions':
        columns = [
          { title: 'ID', field: 'id_concession', width: 80 },
          { title: 'Nom', field: 'nom', editor: 'input' },
          { title: 'Date Création', field: 'date_creation', formatter: (cell) => cell.getValue()?.split('T')[0] || '—' },
        ];
        tabulatorData = data;
        break;
    }

    setTimeout(() => {
      tabulatorRef.current = new Tabulator(tableRef.current, {
        data: tabulatorData,
        columns,
        layout: 'fitDataFill',
        height: 450,
        placeholder: 'Aucune donnée',
        selectableRows: activeTab === 'items',
      });
    }, 50);

  }, [data, activeTab]);

  const handleDeleteSelected = async () => {
    if (!tabulatorRef.current) return;
    const selectedRows = tabulatorRef.current.getSelectedData();
    const ids = selectedRows.map(r => r.id_item);
    if (!ids.length) return;
    if (!window.confirm(`Supprimer ${ids.length} item(s) ?`)) return;

    showSpinner();
    try {
      await apiCall('DELETE', '/items', ids);
      showToast('Items supprimés', 'success');
      const result = await apiCall('GET', '/items');
      setData(result);
    } catch {
      showToast('Erreur suppression', 'danger');
    } finally {
      hideSpinner();
    }
  };

  const handleAddItem = async () => {
    const libelle = prompt('Libellé du nouvel item :');
    if (!libelle) return;
    const concessionId = prompt('ID de la concession (ou laisser vide) :');
    showSpinner();
    try {
      await apiCall('POST', '/items', null, { libelle_canonique: libelle, id_concession: concessionId || null });
      showToast('Item créé', 'success');
      const result = await apiCall('GET', '/items');
      setData(result);
    } catch {
      showToast('Erreur création', 'danger');
    } finally {
      hideSpinner();
    }
  };

  const handleAddConcession = async () => {
    const nom = prompt('Nom de la nouvelle concession :');
    if (!nom) return;
    showSpinner();
    try {
      await apiCall('POST', '/concessions', null, { nom });
      showToast('Concession créée', 'success');
      const result = await apiCall('GET', '/concessions');
      setData(result);
    } catch {
      showToast('Erreur création', 'danger');
    } finally {
      hideSpinner();
    }
  };

  return (
    <div className="max-w-7xl mx-auto space-y-6 animate-fade-in">
      {/* Header */}
      <div>
        <div className="flex items-center gap-2 text-xs font-mono uppercase tracking-wider text-primary-light dark:text-primary-dark mb-1">
          <span className="w-6 h-px bg-primary-light dark:bg-primary-dark" />
          Data Management
        </div>
        <h1 className="font-display text-3xl font-extrabold text-slate-800 dark:text-white">
          Base de <span className="text-primary-light dark:text-primary-dark">données</span>
        </h1>
        <p className="text-slate-500 dark:text-slate-400 mt-1">Gérez les items, colonnes, factures et concessions</p>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="glass kpi-card accent-cyan">
          <span className="text-lg">🏷️</span>
          <span className="kpi-label">Total Items</span>
          <span className="font-display text-2xl font-bold">{data.length}</span>
        </div>
        <div className="glass kpi-card accent-blue">
          <span className="text-lg">📊</span>
          <span className="kpi-label">Colonnes</span>
          <span className="font-display text-2xl font-bold">—</span>
        </div>
        <div className="glass kpi-card accent-pink">
          <span className="text-lg">📄</span>
          <span className="kpi-label">Factures</span>
          <span className="font-display text-2xl font-bold">—</span>
        </div>
        <div className="glass kpi-card accent-green">
          <span className="text-lg">🏢</span>
          <span className="kpi-label">Concessions</span>
          <span className="font-display text-2xl font-bold">{concessionsList.length}</span>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-slate-200 dark:border-slate-700">
        {TABS.map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`tab-btn ${activeTab === tab.id ? 'active' : ''}`}
          >
            <tab.icon size={14} className="inline mr-1" />
            {tab.label}
          </button>
        ))}
      </div>

      {/* Toolbar */}
      <div className="flex justify-between items-center gap-4 flex-wrap">
        <div className="flex gap-2">
          {(activeTab === 'items') && (
            <>
              <button onClick={handleAddItem} className="btn-primary text-sm py-2">
                <Plus size={16} /> Ajouter
              </button>
              <button onClick={handleDeleteSelected} className="btn-glass text-sm text-red-600 dark:text-red-400">
                <Trash2 size={16} /> Supprimer sélection
              </button>
            </>
          )}
          {activeTab === 'concessions' && (
            <button onClick={handleAddConcession} className="btn-primary text-sm py-2">
              <Plus size={16} /> Ajouter
            </button>
          )}
        </div>
        <input
          type="text"
          placeholder="🔍 Rechercher..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="input-glass w-64"
        />
      </div>

      {/* Table */}
      <div className="overflow-x-auto rounded-xl border border-slate-200/30 dark:border-slate-700/30">
        <div ref={tableRef} className="min-h-[400px]" />
      </div>

      {/* Footer */}
      <div className="text-center text-xs font-mono text-slate-400 dark:text-slate-500">
        Total : <span className="text-primary-light dark:text-primary-dark font-bold">{data.length}</span> enregistrements
      </div>
    </div>
  );
}