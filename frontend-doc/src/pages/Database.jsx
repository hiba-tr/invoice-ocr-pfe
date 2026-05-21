import { useState, useEffect, useMemo } from 'react';
import { useApp } from '../context/AppContext';
import { apiCall } from '../api/api';
import { Trash2, Plus, Tag, ColumnsIcon, FileText, Building2, Search } from 'lucide-react';

const TABS = [
  { id: 'items', label: 'Items', icon: Tag },
  { id: 'columns', label: 'Colonnes', icon: ColumnsIcon },
  { id: 'invoices', label: 'Factures', icon: FileText },
  { id: 'concessions', label: 'Concessions', icon: Building2 },
  { id: 'fournisseurs', label: 'Fournisseurs', icon: Building2 },
];

const primaryColor = '#06b6d4';

export default function Database() {
  const { showSpinner, hideSpinner, showToast, concessionsList, setConcessionsList } = useApp();
  const [activeTab, setActiveTab] = useState('items');
  const [data, setData] = useState([]);
  const [search, setSearch] = useState('');
  const [selectedIds, setSelectedIds] = useState(new Set());

  // Charger les concessions au montage
  useEffect(() => {
    apiCall('GET', '/concessions')
      .then(setConcessionsList)
      .catch(() => {});
  }, [setConcessionsList]);

  // Charger les données selon l'onglet actif
  useEffect(() => {
    const fetchData = async () => {
      showSpinner();
      try {
        const endpoints = {
          items: '/items',
          columns: '/colonnes',
          invoices: '/factures',
          concessions: '/concessions',
          fournisseurs: '/fournisseurs',
        };
        const result = await apiCall('GET', endpoints[activeTab]);
        setData(result);
        setSearch('');
        setSelectedIds(new Set());
      } catch {
        showToast('Erreur chargement des données', 'danger');
      } finally {
        hideSpinner();
      }
    };
    fetchData();
  }, [activeTab, hideSpinner, showSpinner, showToast]);

  // Définition des colonnes selon l'onglet
  const columnDefs = useMemo(() => {
    const getConcessionName = (id) => {
      const c = concessionsList.find(c => c.id_concession === id);
      return c ? c.nom : `#${id || '—'}`;
    };

    switch (activeTab) {
      case 'items':
        return [
          { key: 'id_item', label: 'ID', align: 'left', width: '5rem' },
          { key: 'libelle_canonique', label: 'Libellé', align: 'left' },
          {
            key: 'id_concession', label: 'Concession', align: 'center', width: '10rem',
            render: (v) => getConcessionName(v),
          },
          {
            key: 'statut', label: 'Statut', align: 'center', width: '8rem',
            render: (v) => {
              if (v === 'fusionne') return (
                <span className="badge-status bg-amber-100 dark:bg-amber-900/30 text-amber-700 dark:text-amber-400">Fusionné</span>
              );
              if (v === 'actif') return (
                <span className="badge-status badge-success">Actif</span>
              );
              return <span className="text-slate-400">{v || '—'}</span>;
            },
          },
          {
            key: 'usage_count', label: 'Utilisations', align: 'center', width: '9rem',
            render: (v) => v > 0
              ? <span className="badge-status badge-success">{v} facture(s)</span>
              : <span className="text-slate-400">—</span>,
          },
          {
            key: 'date_derniere_util', label: 'Dernière utilisation', align: 'left', width: '12rem',
            render: (v) => v?.split('T')[0] || '—',
          },
        ];

      case 'columns':
        return [
          { key: 'id_colonne', label: 'ID', align: 'left', width: '5rem' },
          { key: 'libelle_canonique', label: 'Libellé', align: 'left' },
          {
            key: 'id_concession', label: 'Concession', align: 'center', width: '10rem',
            render: (v) => getConcessionName(v),
          },
          {
            key: 'usage_count', label: 'Utilisations', align: 'center', width: '8rem',
            render: (v) => v > 0
              ? <span className="badge-status badge-success">{v}</span>
              : <span className="text-slate-400">—</span>,
          },
        ];

      case 'invoices':
        return [
          { key: 'id_facture', label: 'ID', align: 'left', width: '5rem' },
          { key: 'date_facture', label: 'Date', align: 'left', width: '10rem', render: (v) => v?.split('T')[0] || '—' },
          {
            key: 'id_concession', label: 'Concession', align: 'left',
            render: (v) => getConcessionName(v),
          },
          { key: 'fichier_source', label: 'Fichier', align: 'left' },
          {
            key: 'total_montant', label: 'Montant', align: 'right', width: '9rem',
            render: (v) => `${(v || 0).toFixed(2)} €`,
          },
        ];

      case 'concessions':
        return [
          { key: 'id_concession', label: 'ID', align: 'left', width: '5rem' },
          { key: 'nom', label: 'Nom', align: 'left' },
          { key: 'date_creation', label: 'Date création', align: 'left', width: '12rem', render: (v) => v?.split('T')[0] || '—' },
        ];

      case 'fournisseurs':
        return [
          { key: 'id_fournisseur', label: 'ID', align: 'left', width: '5rem' },
          { key: 'nom', label: 'Nom', align: 'left' },
          { key: 'nom_normalise', label: 'Nom normalisé', align: 'left' },
          { key: 'pays', label: 'Pays', align: 'left', width: '7rem' },
        ];

      default:
        return [];
    }
  }, [activeTab, concessionsList]);

  // Filtrage de la recherche
  const filteredData = useMemo(() => {
    if (!search.trim()) return data;
    const q = search.toLowerCase();
    return data.filter(row =>
      Object.values(row).some(v => String(v ?? '').toLowerCase().includes(q))
    );
  }, [data, search]);

  // Sélection (uniquement pour items)
  const toggleSelect = (id) => {
    setSelectedIds(prev => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const toggleSelectAll = () => {
    if (selectedIds.size === filteredData.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(filteredData.map(r => r.id_item)));
    }
  };

  // Actions
  const handleDeleteSelected = async () => {
    const ids = [...selectedIds];
    if (!ids.length) return;
    if (!window.confirm(`Supprimer ${ids.length} item(s) ?`)) return;
    showSpinner();
    try {
      await apiCall('DELETE', '/items', ids);
      showToast('Items supprimés', 'success');
      const result = await apiCall('GET', '/items');
      setData(result);
      setSelectedIds(new Set());
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
      setData(await apiCall('GET', '/items'));
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
      setData(await apiCall('GET', '/colonnes'));
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
      setData(await apiCall('GET', '/concessions'));
    } catch {
      showToast('Erreur création', 'danger');
    } finally {
      hideSpinner();
    }
  };

  const kpiCounts = {
    items: data.length,
    columns: activeTab === 'columns' ? data.length : '—',
    invoices: activeTab === 'invoices' ? data.length : '—',
    concessions: concessionsList.length,
  };

  return (
    <div className="max-w-7xl mx-auto space-y-6 animate-fade-in">
      {/* Header */}
      <div>
        <div className="flex items-center gap-2 text-xs font-mono uppercase tracking-wider mb-1" style={{ color: primaryColor }}>
          <span className="w-6 h-px" style={{ background: primaryColor }} />
          Data Management
        </div>
        <h1 className="font-display text-3xl font-extrabold text-slate-800 dark:text-white">
          Base de <span style={{ color: primaryColor }}>données</span>
        </h1>
        <p className="text-slate-500 dark:text-slate-400 mt-1">Gérez les items, colonnes, factures et concessions</p>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="glass kpi-card accent-cyan">
          <span className="text-lg">🏷️</span>
          <span className="kpi-label">Total Items</span>
          <span className="font-display text-2xl font-bold">{kpiCounts.items}</span>
        </div>
        <div className="glass kpi-card accent-blue">
          <span className="text-lg">📊</span>
          <span className="kpi-label">Colonnes</span>
          <span className="font-display text-2xl font-bold">{kpiCounts.columns}</span>
        </div>
        <div className="glass kpi-card accent-pink">
          <span className="text-lg">📄</span>
          <span className="kpi-label">Factures</span>
          <span className="font-display text-2xl font-bold">{kpiCounts.invoices}</span>
        </div>
        <div className="glass kpi-card accent-green">
          <span className="text-lg">🏢</span>
          <span className="kpi-label">Concessions</span>
          <span className="font-display text-2xl font-bold">{kpiCounts.concessions}</span>
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
              <button
                onClick={handleDeleteSelected}
                disabled={selectedIds.size === 0}
                className="btn-glass text-sm text-red-600 dark:text-red-400 disabled:opacity-40 disabled:cursor-not-allowed"
              >
                <Trash2 size={16} /> Supprimer ({selectedIds.size})
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
        <div className="relative">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            type="text"
            placeholder="Rechercher..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="input-glass w-64 pl-9"
          />
        </div>
      </div>

      {/* Table — même style que History.jsx */}
      <div className="overflow-x-auto rounded-xl border border-slate-200/30 dark:border-slate-700/30">
        <table className="w-full text-sm" style={{ minWidth: '100%' }}>
          <thead>
            <tr className="bg-gradient-to-r from-blue-50/80 to-cyan-50/80 dark:from-blue-950/30 dark:to-cyan-950/20">
              {activeTab === 'items' && (
                <th className="px-4 py-3 w-10">
                  <input
                    type="checkbox"
                    checked={filteredData.length > 0 && selectedIds.size === filteredData.length}
                    onChange={toggleSelectAll}
                    className="rounded cursor-pointer accent-cyan-500"
                  />
                </th>
              )}
              {columnDefs.map(col => (
                <th
                  key={col.key}
                  className="px-4 py-3 text-left font-mono text-xs uppercase tracking-wider whitespace-nowrap"
                  style={{ color: primaryColor, width: col.width }}
                >
                  {col.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-blue-100/50 dark:divide-slate-800/50">
            {filteredData.length === 0 ? (
              <tr>
                <td
                  colSpan={columnDefs.length + (activeTab === 'items' ? 1 : 0)}
                  className="px-4 py-10 text-center text-slate-400 dark:text-slate-500 italic"
                >
                  Aucune donnée
                </td>
              </tr>
            ) : (
              filteredData.map((row, i) => {
                const rowId = row.id_item ?? row.id_colonne ?? row.id_facture ?? row.id_concession ?? row.id_fournisseur ?? i;
                const isSelected = activeTab === 'items' && selectedIds.has(row.id_item);
                return (
                  <tr
                    key={rowId}
                    className={`transition-colors ${
                      isSelected
                        ? 'bg-cyan-50/60 dark:bg-cyan-950/20'
                        : 'hover:bg-blue-50/30 dark:hover:bg-slate-800/30'
                    }`}
                  >
                    {activeTab === 'items' && (
                      <td className="px-4 py-3">
                        <input
                          type="checkbox"
                          checked={isSelected}
                          onChange={() => toggleSelect(row.id_item)}
                          className="rounded cursor-pointer accent-cyan-500"
                        />
                      </td>
                    )}
                    {columnDefs.map((col) => {
                      const value = row[col.key];
                      const rendered = col.render ? col.render(value) : (value ?? '—');
                      return (
                        <td
                          key={col.key}
                          className={`px-4 py-3 whitespace-nowrap ${
                            col.align === 'right'
                              ? 'font-mono text-right text-slate-600 dark:text-slate-400'
                              : col.align === 'center'
                              ? 'text-center'
                              : col.key.includes('libelle') || col.key === 'nom'
                              ? 'font-medium text-slate-800 dark:text-slate-200'
                              : 'text-slate-600 dark:text-slate-400'
                          }`}
                        >
                          {rendered}
                        </td>
                      );
                    })}
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {/* Footer */}
      <div className="text-center text-xs font-mono text-slate-400 dark:text-slate-500">
        Total : <span className="font-bold" style={{ color: primaryColor }}>{filteredData.length}</span>
        {search && ` / ${data.length}`} enregistrement(s)
      </div>

      {/* Stats items */}
      {activeTab === 'items' && data.length > 0 && (
        <div className="glass-card text-xs text-slate-500 dark:text-slate-400">
          <span className="font-mono uppercase tracking-wider">Répartition : </span>
          Actifs: {data.filter(i => i.statut === 'actif').length} |
          Fusionnés: {data.filter(i => i.statut === 'fusionne').length} |
          Avec usage: {data.filter(i => i.usage_count > 0).length}
        </div>
      )}
    </div>
  );
}