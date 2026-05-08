import { useState, useEffect, useRef } from 'react';
import { apiCall } from '../api/api';
import { TabulatorFull as Tabulator } from 'tabulator-tables';
import { Database as DbIcon, Trash2 } from 'lucide-react';

export default function Database() {
  const [activeTab, setActiveTab] = useState('invoices');
  const [data, setData] = useState([]);
  const tableRef = useRef(null);
  const tabulatorInst = useRef(null);

  useEffect(() => {
    const fetchData = async () => {
      try {
        let endpoint = '';
        if (activeTab === 'items') endpoint = '/items';
        else if (activeTab === 'columns') endpoint = '/colonnes';
        else if (activeTab === 'invoices') endpoint = '/factures';
        else if (activeTab === 'concessions') endpoint = '/concessions';
        
        const result = await apiCall('GET', endpoint);
        setData(result);
      } catch (e) {
        console.error('Erreur chargement base de données', e); // 'e' est utilisé
      }
    };
    fetchData();
  }, [activeTab]);

  useEffect(() => {
    if (data && tableRef.current) {
      let columns = [];
      if (activeTab === 'invoices') {
        columns = [
          { title: "ID", field: "id_facture", width: 80, headerSort: false },
          { title: "Date", field: "date_facture" },
          { title: "Concession", field: "id_concession" },
          { title: "Fichier source", field: "fichier_source" },
        ];
      } else if (activeTab === 'items') {
        columns = [
          { formatter: "rowSelection", titleFormatter: "rowSelection", hozAlign: "center", headerSort: false, width: 50 },
          { title: "ID", field: "id_item", width: 80 },
          { title: "Libellé Canonique", field: "libelle_canonique" },
          { title: "Concession", field: "id_concession" },
        ];
      } else if (activeTab === 'columns') {
        columns = [
          { title: "ID", field: "id_colonne", width: 80 },
          { title: "Libellé", field: "libelle_canonique" },
          { title: "Concession", field: "id_concession" },
        ];
      } else if (activeTab === 'concessions') {
        columns = [
          { title: "ID", field: "id_concession", width: 80 },
          { title: "Nom", field: "nom" },
          { title: "Date Création", field: "date_creation" },
        ];
      }

      tabulatorInst.current = new Tabulator(tableRef.current, {
        data: data,
        layout: "fitColumns",
        columns: columns,
        selectableRows: activeTab === 'items' ? true : false,
      });
    }
  }, [data, activeTab]);

  const handleDeleteItems = async () => {
    if (!tabulatorInst.current) return;
    const selectedRows = tabulatorInst.current.getSelectedData();
    const selectedIds = selectedRows.map(row => row.id_item);
    
    if (selectedIds.length === 0) return;
    if (!window.confirm(`Supprimer ${selectedIds.length} item(s) ?`)) return;

    try {
      await apiCall('DELETE', '/items', selectedIds);
      const result = await apiCall('GET', '/items');
      setData(result);
    } catch (e) {
      console.error(e); // 'e' est utilisé
      alert("Erreur lors de la suppression");
    }
  };

  const tabs = [
    { id: 'invoices', label: 'Factures' },
    { id: 'concessions', label: 'Fournisseurs' },
    { id: 'items', label: 'Articles' },
    { id: 'columns', label: 'Schémas (Colonnes)' }
  ];

  return (
    <div className="space-y-6 fade-in">
      <h2 className="text-2xl font-bold flex items-center gap-2 text-slate-800 dark:text-white">
        <DbIcon className="text-primary" /> Base de données
      </h2>

      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl overflow-hidden shadow-sm">
        <div className="flex border-b border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/50">
          {tabs.map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`px-6 py-4 font-medium transition-colors ${
                activeTab === tab.id 
                  ? 'text-primary dark:text-cyan border-b-2 border-primary dark:border-cyan bg-white dark:bg-white/5' 
                  : 'text-slate-500 dark:text-slate-400 hover:text-slate-800 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-white/5'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        <div className="p-6">
          {activeTab === 'items' && (
            <div className="mb-4 flex justify-end">
              <button 
                onClick={handleDeleteItems} 
                className="bg-red-50 dark:bg-red-500/10 text-red-600 dark:text-red-400 border border-red-200 dark:border-red-500/30 hover:bg-red-100 dark:hover:bg-red-500/20 px-4 py-2 rounded-lg flex items-center gap-2 transition-colors font-medium"
              >
                <Trash2 size={18} /> Supprimer sélection
              </button>
            </div>
          )}
          
          <div ref={tableRef} className="w-full min-h-[400px] border border-slate-200 dark:border-slate-800 rounded-lg"></div>
        </div>
      </div>
    </div>
  );
}