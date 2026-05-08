import { useState, useEffect, useRef } from 'react';
import { apiCall } from '../api/api';
import { TabulatorFull as Tabulator } from 'tabulator-tables';
import { PenTool, Plus, Save } from 'lucide-react';

export default function Manual() {
  const [concessions, setConcessions] = useState([]);
  const [selectedConcession, setSelectedConcession] = useState('');
  
  const [showItemsModal, setShowItemsModal] = useState(false);
  const [showColsModal, setShowColsModal] = useState(false);
  const [availableItems, setAvailableItems] = useState([]);
  const [availableCols, setAvailableCols] = useState([]);
  const [selectedItemsList, setSelectedItemsList] = useState([]);

  const tableRef = useRef(null);
  const tabulatorInst = useRef(null);

  useEffect(() => {
    const fetchConcessions = async () => {
      try {
        const result = await apiCall('GET', '/concessions');
        setConcessions(result);
      } catch (e) {
        console.error("Erreur chargement concessions", e); // 'e' est utilisé
      }
    };
    fetchConcessions();
  }, []);

  const selectConcession = async (id) => {
    setSelectedConcession(id);
    if(!id) return;
    try {
        const items = await apiCall('GET', '/items', null, { id_concession: id });
        const itemsList = items.map(it => it.libelle_canonique).filter(Boolean);
        if (itemsList.length > 0) {
            setAvailableItems(itemsList);
            setShowItemsModal(true);
        } else {
            promptCols([]);
        }
    } catch(e) {
        console.error("Erreur chargement items:", e); // 'e' est utilisé
    }
  };

  const promptCols = async (descriptions) => {
      setSelectedItemsList(descriptions);
      try {
          const colonnes = await apiCall('GET', '/colonnes', null, { id_concession: selectedConcession });
          const colsList = colonnes.map(c => c.libelle_canonique);
          if (colsList.length === 0) {
              finalizeTable(['Description', 'Montant'], descriptions);
          } else {
              setAvailableCols(colsList);
              setShowColsModal(true);
          }
      } catch(e) {
          console.error("Erreur chargement colonnes:", e); // 'e' est utilisé
      }
  };

  const finalizeTable = (cols, descList) => {
      let colDefs = [{ title: "Description", field: "description", editor: "input", width: 250 }];
      cols.filter(c => c !== 'Description').forEach(c => colDefs.push({ title: c, field: c, editor: "input" }));
      
      let rows = descList.map(d => ({ description: d }));
      if(rows.length === 0) rows = [{}];

      if (tabulatorInst.current) tabulatorInst.current.destroy();
      tabulatorInst.current = new Tabulator(tableRef.current, {
        data: rows, layout: "fitColumns", columns: colDefs, editable: true,
      });
  };

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold text-slate-800 dark:text-white"><PenTool className="inline mr-2"/> Saisie Manuelle</h2>

      <div className="bg-white dark:bg-slate-900 p-6 rounded-xl border border-slate-200 dark:border-slate-800">
        <label className="block mb-2 text-sm font-semibold text-slate-500 uppercase tracking-wider">1. Sélectionner Concession</label>
        <select value={selectedConcession} onChange={(e) => selectConcession(e.target.value)} className="w-full bg-slate-50 dark:bg-slate-800 p-3 rounded border border-slate-200 dark:border-slate-700 outline-none focus:border-primary">
            <option value="">-- Choisir --</option>
            {concessions.map(c => <option key={c.id_concession} value={c.id_concession}>{c.nom}</option>)}
        </select>
      </div>

      <div className="bg-white dark:bg-slate-900 p-6 rounded-xl border border-slate-200 dark:border-slate-800">
          <div className="flex justify-between items-center mb-4">
              <h3 className="font-bold text-slate-800 dark:text-white">2. Lignes de facturation</h3>
              <button onClick={() => tabulatorInst.current?.addRow({})} className="bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700 px-3 py-1.5 rounded-lg text-sm transition-colors">
                <Plus size={16} className="inline mr-1"/> Ajouter Ligne
              </button>
          </div>
          <div ref={tableRef} className="min-h-[300px] border border-slate-200 dark:border-slate-700 rounded-lg overflow-hidden"></div>
          <div className="mt-6 flex justify-end">
              <button className="bg-primary hover:bg-blue-700 transition-colors text-white px-6 py-2.5 rounded-lg font-bold flex items-center gap-2 shadow-sm">
                <Save size={18}/> Enregistrer la facture
              </button>
          </div>
      </div>

      {showItemsModal && (
        <div className="fixed inset-0 bg-slate-900/50 backdrop-blur-sm flex items-center justify-center z-50">
            <div className="bg-white dark:bg-slate-900 p-6 rounded-xl w-96 max-h-[80vh] overflow-y-auto border border-slate-200 dark:border-slate-800 shadow-xl">
                <h3 className="font-bold mb-4 text-slate-800 dark:text-white">Items existants</h3>
                {availableItems.map((item, i) => (
                    <label key={i} className="flex items-center gap-3 mb-2 p-3 hover:bg-slate-50 dark:hover:bg-slate-800 rounded-lg cursor-pointer transition-colors border border-transparent hover:border-slate-200 dark:hover:border-slate-700">
                        <input type="checkbox" value={item} id={`item-${i}`} className="rounded border-slate-300" /> 
                        <span className="text-slate-700 dark:text-slate-300">{item}</span>
                    </label>
                ))}
                <button onClick={() => {
                    const checked = Array.from(document.querySelectorAll('input[id^="item-"]:checked')).map(cb => cb.value);
                    setShowItemsModal(false);
                    promptCols(checked);
                }} className="mt-6 w-full bg-primary hover:bg-blue-700 text-white py-2.5 rounded-lg font-bold transition-colors">Étape Suivante</button>
            </div>
        </div>
      )}

      {showColsModal && (
        <div className="fixed inset-0 bg-slate-900/50 backdrop-blur-sm flex items-center justify-center z-50">
            <div className="bg-white dark:bg-slate-900 p-6 rounded-xl w-96 border border-slate-200 dark:border-slate-800 shadow-xl">
                <h3 className="font-bold mb-4 text-slate-800 dark:text-white">Colonnes à afficher</h3>
                {availableCols.map((col, i) => (
                    <label key={i} className="flex items-center gap-3 mb-2 p-2">
                        <input type="checkbox" value={col} id={`col-${i}`} defaultChecked className="rounded border-slate-300" /> 
                        <span className="text-slate-700 dark:text-slate-300">{col}</span>
                    </label>
                ))}
                <button onClick={() => {
                    const checked = Array.from(document.querySelectorAll('input[id^="col-"]:checked')).map(cb => cb.value);
                    setShowColsModal(false);
                    finalizeTable(checked, selectedItemsList);
                }} className="mt-6 w-full bg-primary hover:bg-blue-700 text-white py-2.5 rounded-lg font-bold transition-colors">Terminer et afficher</button>
            </div>
        </div>
      )}
    </div>
  );
}