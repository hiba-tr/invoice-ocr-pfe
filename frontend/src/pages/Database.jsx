import { useState, useEffect, useRef } from 'react';
import { useApp } from '../context/AppContext';
import { apiCall } from '../api/api';
import { TabulatorFull as Tabulator } from 'tabulator-tables';
import 'tabulator-tables/dist/css/tabulator.min.css';
import { Trash2, Plus, Tag, ColumnsIcon, FileText, Building2 } from 'lucide-react';

const TABS = [
  { id: 'items', label: 'Items', icon: Tag },
  { id: 'columns', label: 'Colonnes', icon: ColumnsIcon },
  { id: 'invoices', label: 'Factures', icon: FileText },
  { id: 'concessions', label: 'Concessions', icon: Building2 },
  { id: 'fournisseurs', label: 'Fournisseurs', icon: Building2 },
];

export default function Database() {
  const { showSpinner, hideSpinner, showToast, concessionsList, setConcessionsList } = useApp();
  const [activeTab, setActiveTab] = useState('items');
  const [search, setSearch] = useState('');
  const tableRef = useRef(null);
  const tabulatorRef = useRef(null);

  // États séparés pour chaque entité (chargées une seule fois au montage)
  const [items, setItems] = useState([]);
  const [columnsData, setColumnsData] = useState([]);  // renommé pour éviter conflit avec la variable `columns` Tabulator
  const [invoices, setInvoices] = useState([]);
  const [concessions, setConcessions] = useState([]);
  const [fournisseurs, setFournisseurs] = useState([]);

  // Chargement initial unique de toutes les données
  useEffect(() => {
    const loadAll = async () => {
      showSpinner();
      try {
        const [itemsRes, columnsRes, invoicesRes, concessionsRes, fournisseursRes] = await Promise.all([
          apiCall('GET', '/items'),
          apiCall('GET', '/colonnes'),
          apiCall('GET', '/factures'),
          apiCall('GET', '/concessions'),
          apiCall('GET', '/fournisseurs'),
        ]);
        setItems(itemsRes);
        setColumnsData(columnsRes);
        setInvoices(invoicesRes);
        setConcessions(concessionsRes);
        setFournisseurs(fournisseursRes);
        // Mettre à jour la liste des concessions dans le contexte si nécessaire
        setConcessionsList(concessionsRes);
      } catch (err) {
        showToast('Erreur de chargement des données', 'danger');
      } finally {
        hideSpinner();
      }
    };
    loadAll();
  }, []); // exécuté une seule fois

  // Initialiser Tabulator selon l'onglet actif (pas de nouvel appel API)
  useEffect(() => {
    if (!tableRef.current) return;

    // Détruire l'instance précédente
    if (tabulatorRef.current) {
      tabulatorRef.current.destroy();
      tabulatorRef.current = null;
    }

    let tabulatorData = [];
    let columns = [];

    switch (activeTab) {
      case 'items':
        columns = [
          { title: 'ID', field: 'id_item', width: 80, frozen: true },
          { title: 'Libellé', field: 'libelle_canonique', editor: 'input', headerFilter: true },
          { title: 'Concession', field: 'id_concession', width: 120, hozAlign: 'center',
            formatter: (cell) => {
              const cid = cell.getValue();
              const concession = concessionsList.find(c => c.id_concession === cid);
              return concession ? concession.nom : `#${cid || '—'}`;
            }
          },
          { title: 'Statut', field: 'statut', width: 110, hozAlign: 'center',
            formatter: (cell) => {
              const v = cell.getValue();
              if (v === 'fusionne') return '<span class="badge-status badge-warning">Fusionné</span>';
              if (v === 'actif') return '<span class="badge-status badge-success">Actif</span>';
              return `<span class="text-slate-400">${v || '—'}</span>`;
            }
          },
          { title: 'Utilisations', field: 'usage_count', width: 110, hozAlign: 'center',
            formatter: (cell) => {
              const v = cell.getValue();
              return v > 0 ? `<span class="badge-status badge-success">${v} facture(s)</span>` : '<span class="text-slate-400">—</span>';
            }
          },
          { title: 'Dernière utilisation', field: 'date_derniere_util', width: 160,
            formatter: (cell) => cell.getValue()?.split('T')[0] || '—'
          },
        ];
        tabulatorData = items;
        break;

      case 'columns':
        columns = [
          { title: 'ID', field: 'id_colonne', width: 80 },
          { title: 'Libellé', field: 'libelle_canonique', editor: 'input', headerFilter: true },
          { title: 'Concession', field: 'id_concession', width: 120, hozAlign: 'center',
            formatter: (cell) => {
              const cid = cell.getValue();
              const concession = concessionsList.find(c => c.id_concession === cid);
              return concession ? concession.nom : `#${cid || '—'}`;
            }
          },
          { title: 'Utilisations', field: 'usage_count', width: 100, hozAlign: 'center',
            formatter: 'tickCross',
          },
        ];
        tabulatorData = columnsData;
        break;

      case 'invoices':
        columns = [
          { title: 'ID', field: 'id_facture', width: 80 },
          { title: 'Date', field: 'date_facture', formatter: (cell) => cell.getValue()?.split('T')[0] || '—' },
          { title: 'Concession', field: 'id_concession',
            formatter: (cell) => {
              const cid = cell.getValue();
              const concession = concessionsList.find(c => c.id_concession === cid);
              return concession ? concession.nom : `#${cid || '—'}`;
            }
          },
          { title: 'Fichier', field: 'fichier_source' },
          { title: 'Montant', field: 'total_montant', hozAlign: 'right',
            formatter: (cell) => `${(cell.getValue() || 0).toFixed(2)} €`
          },
        ];
        tabulatorData = invoices;
        break;

      case 'concessions':
        columns = [
          { title: 'ID', field: 'id_concession', width: 80 },
          { title: 'Nom', field: 'nom', editor: 'input' },
          { title: 'Nom normalisé', field: 'nom_normalise', visible: false },
          { title: 'Date création', field: 'date_creation', formatter: (cell) => cell.getValue()?.split('T')[0] || '—' },
        ];
        tabulatorData = concessions;
        break;

      case 'fournisseurs':
        columns = [
          { title: 'ID', field: 'id_fournisseur', width: 80 },
          { title: 'Nom', field: 'nom', editor: 'input' },
          { title: 'Nom normalisé', field: 'nom_normalise' },
          { title: 'Pays', field: 'pays', width: 100 },
        ];
        tabulatorData = fournisseurs;
        break;
    }

    // Créer la nouvelle instance Tabulator
    tabulatorRef.current = new Tabulator(tableRef.current, {
      data: tabulatorData,
      columns,
      layout: 'fitDataFill',
      height: 450,
      placeholder: 'Aucune donnée',
      selectableRows: activeTab === 'items',
    });

  }, [activeTab, items, columnsData, invoices, concessions, fournisseurs, concessionsList]);

  // ---- Actions (ajout / suppression) ----
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
      // Recharger uniquement la liste des items
      const newItems = await apiCall('GET', '/items');
      setItems(newItems);
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
      await apiCall('POST', '/items', { libelle_canonique: libelle, id_concession: concessionId || null });
      showToast('Item créé', 'success');
      const newItems = await apiCall('GET', '/items');
      setItems(newItems);
    } catch {
      showToast('Erreur création', 'danger');
    } finally {
      hideSpinner();
    }
  };

  const handleAddColumn = async () => {
    const libelle = prompt('Libellé de la nouvelle colonne :');
    if (!libelle) return;
    const concessionId = prompt('ID de la concession (ou laisser vide) :');
    showSpinner();
    try {
      await apiCall('POST', '/colonnes', { libelle_canonique: libelle, id_concession: concessionId || null });
      showToast('Colonne créée', 'success');
      const newColumns = await apiCall('GET', '/colonnes');
      setColumnsData(newColumns);
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
      const newC = await apiCall('POST', '/concessions', { nom });
      setConcessionsList(prev => [...prev, newC]);
      showToast('Concession créée', 'success');
      const newConcessions = await apiCall('GET', '/concessions');
      setConcessions(newConcessions);
    } catch {
      showToast('Erreur création', 'danger');
    } finally {
      hideSpinner();
    }
  };

  // ---- Rendu ----
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
        <p className="text-slate-500 dark:text-slate-400 mt-1">Gérez les items, colonnes, factures, concessions et fournisseurs</p>
      </div>

      {/* KPI Cards – uniquement Factures, Concessions, Fournisseurs */}
      <div className="grid grid-cols-3 gap-4">
        <div className="glass kpi-card accent-cyan">
          <span className="text-lg">📄</span>
          <span className="kpi-label">Factures</span>
          <span className="font-display text-2xl font-bold">{invoices.length}</span>
        </div>
        <div className="glass kpi-card accent-green">
          <span className="text-lg">🛢️</span>
          <span className="kpi-label">Concessions</span>
          <span className="font-display text-2xl font-bold">{concessions.length}</span>
        </div>
        <div className="glass kpi-card accent-pink">
          <span className="text-lg">🚚</span>
          <span className="kpi-label">Fournisseurs</span>
          <span className="font-display text-2xl font-bold">{fournisseurs.length}</span>
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
          {activeTab === 'items' && (
            <>
              <button onClick={handleAddItem} className="btn-primary text-sm py-2">
                <Plus size={16} /> Ajouter
              </button>
              <button onClick={handleDeleteSelected} className="btn-glass text-sm text-red-600 dark:text-red-400">
                <Trash2 size={16} /> Supprimer sélection
              </button>
            </>
          )}
          {activeTab === 'columns' && (
            <button onClick={handleAddColumn} className="btn-primary text-sm py-2">
              <Plus size={16} /> Ajouter
            </button>
          )}
          {activeTab === 'concessions' && (
            <button onClick={handleAddConcession} className="btn-primary text-sm py-2">
              <Plus size={16} /> Ajouter
            </button>
          )}
        </div>
        <input
          type="text"
          placeholder="Rechercher..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="input-glass w-64"
        />
      </div>

      {/* Table Tabulator */}
      <div className="overflow-x-auto rounded-xl border border-slate-200/30 dark:border-slate-700/30">
        <div ref={tableRef} className="min-h-[400px]" />
      </div>

      {/* Footer */}
      <div className="text-center text-xs font-mono text-slate-400 dark:text-slate-500">
        Total : <span className="text-primary-light dark:text-primary-dark font-bold">
          {activeTab === 'items' && items.length}
          {activeTab === 'columns' && columnsData.length}
          {activeTab === 'invoices' && invoices.length}
          {activeTab === 'concessions' && concessions.length}
          {activeTab === 'fournisseurs' && fournisseurs.length}
        </span> enregistrements
      </div>

      {/* Stats matching (seulement pour items) */}
      {activeTab === 'items' && items.length > 0 && (
        <div className="glass-card text-xs text-slate-500 dark:text-slate-400">
          <span className="font-mono uppercase tracking-wider">Répartition : </span>
          Actifs: {items.filter(i => i.statut === 'actif').length} |
          Fusionnés: {items.filter(i => i.statut === 'fusionne').length} |
          Avec usage: {items.filter(i => i.usage_count > 0).length}
        </div>
      )}
    </div>
  );
}