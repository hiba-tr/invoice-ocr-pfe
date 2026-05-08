import { useState, useEffect, useRef } from 'react';
import { apiCall, API_BASE } from '../api/api';
import axios from 'axios';
import { TabulatorFull as Tabulator } from 'tabulator-tables';
import { UploadCloud, CheckCircle, Save, Download, Plus, Columns } from 'lucide-react';

export default function Upload() {
  const [file, setFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [extraction, setExtraction] = useState(null);
  const [concessions, setConcessions] = useState([]);
  
  const [concessionId, setConcessionId] = useState('');
  const [newConcessionName, setNewConcessionName] = useState('');
  const [meta, setMeta] = useState({ date: '', fournisseur: '', currency: 'TND' });
  const [forceOverwrite, setForceOverwrite] = useState(false);

  const tableRef = useRef(null);
  const tabulatorInst = useRef(null);

  // Fonction de nettoyage
  const cleanValue = (val) => {
    if (val === null || val === undefined) return "";
    if (typeof val === 'number') return String(val);
    return String(val).replace(/\s+/g, ' ').trim();
  };

  useEffect(() => {
    apiCall('GET', '/concessions')
      .then(setConcessions)
      .catch(e => console.error("Erreur concessions:", e));
  }, []);

  const handleExtract = async () => {
    if (!file) {
      alert("Veuillez d'abord choisir un fichier !");
      return;
    }
    setLoading(true);
    try {
      const formData = new FormData();
      formData.append('file', file);
      const resp = await axios.post(`${API_BASE}/upload`, formData);
      const inv = resp.data.invoices ? resp.data.invoices[0] : resp.data;
      setExtraction(inv);
      
      if (inv.metadata) {
        setMeta({
          date: inv.metadata.date || '', 
          fournisseur: inv.metadata.company || inv.metadata.fournisseur || '',
          currency: inv.metadata.currency || 'TND', 
        });
        
        if (inv.metadata.concession) {
          const match = await apiCall('GET', '/match-concession', null, { nom_extrait: inv.metadata.concession });
          if (match.matched) setConcessionId(match.concession_id);
        }
      }
    } catch (e) {
      console.error("Erreur d'extraction:", e);
      alert("Erreur lors de l'extraction IA");
    } finally {
      setLoading(false);
    }
  };

  // ==================== TABLEAU CORRIGÉ ====================
  useEffect(() => {
    if (!extraction?.items || !tableRef.current) return;

    if (tabulatorInst.current) {
      tabulatorInst.current.destroy();
      tabulatorInst.current = null;
    }

    const originalColumns = extraction.columns || [];
    const cleanedColumns = originalColumns.map(col => String(col).trim());

    const colMap = {};

    const columns = [
      {
        title: extraction.metadata?.first_column_name || "Description",
        field: "description",
        editor: "input",
        width: 450,                    // ← Plus large
        frozen: true,
        headerTooltip: "Description",
        formatter: "plaintext",
      },
    ];

    cleanedColumns.forEach((col, index) => {
      const safeField = `col_${index}_${col.replace(/[^a-zA-Z0-9]/g, "_")}`;
      colMap[col] = safeField;

      columns.push({
        title: col,
        field: safeField,
        editor: "input",
        minWidth: 130,
        headerTooltip: col,
        hozAlign: "center",
        vertAlign: "middle",
      });
    });

    const tableData = extraction.items.map((item, idx) => {
      let description = cleanValue(item.description || item.libelle || "");

      const row = { id: idx, description };

      // Initialiser les colonnes
      Object.values(colMap).forEach(field => row[field] = "");

      const valeurs = item.valeurs;

      if (Array.isArray(valeurs)) {
        // Cas le plus fréquent
        valeurs.forEach((val, i) => {
          if (i < cleanedColumns.length) {
            const safeField = colMap[cleanedColumns[i]];
            if (safeField) {
              row[safeField] = cleanValue(val);
            }
          }
        });
      } 
      else if (valeurs && typeof valeurs === "object" && !Array.isArray(valeurs)) {
        // Cas objet { "Nom Colonne": valeur }
        Object.entries(valeurs).forEach(([key, value]) => {
          const trimmedKey = key.trim();
          let safeField = colMap[trimmedKey];

          if (!safeField) {
            const colIndex = cleanedColumns.findIndex(c => c === trimmedKey);
            if (colIndex !== -1) safeField = colMap[cleanedColumns[colIndex]];
          }

          if (safeField) row[safeField] = cleanValue(value);
        });
      } 
      else if (valeurs !== undefined && valeurs !== null) {
        // Valeur unique
        if (cleanedColumns.length > 0) {
          const safeField = colMap[cleanedColumns[0]];
          if (safeField) row[safeField] = cleanValue(valeurs);
        }
      }

      return row;
    });

    setTimeout(() => {
      tabulatorInst.current = new Tabulator(tableRef.current, {
        data: tableData,
        columns,
        layout: "fitColumns",
        responsiveLayout: "collapse",
        movableColumns: true,
        resizableColumns: true,
        height: "520px",
        placeholder: "Aucune donnée détectée",
        clipboard: true,
        history: true,
        columnDefaults: {
          tooltip: true,
          vertAlign: "middle",
          hozAlign: "center",
          headerHozAlign: "center",
          resizable: true,
          minWidth: 140,
        },
        rowHeight: 62,
      });
    }, 80);

  }, [extraction]);

  const handleCreateConcession = async () => {
    if (!newConcessionName) return;
    try {
      const newC = await apiCall('POST', '/concessions', null, { nom: newConcessionName });
      setConcessions([...concessions, newC]);
      setConcessionId(newC.id_concession);
      setNewConcessionName('');
    } catch (e) { 
      console.error(e);
      alert("Erreur création concession"); 
    }
  };

  const saveFacture = async () => {
    if (!concessionId) {
      alert("⚠️ Sélectionnez une Concession.");
      return;
    }
    if (!tabulatorInst.current) return;

    setLoading(true);
    try {
      const itemsData = tabulatorInst.current.getData().map(row => {
        const { description, ...valeurs } = row;
        const cleanedValeurs = {};
        Object.entries(valeurs).forEach(([k, v]) => {
          if (v !== undefined && v !== null && v !== '') {
            cleanedValeurs[k] = cleanValue(v);
          }
        });
        return { 
          description: cleanValue(description || ''), 
          valeurs: cleanedValeurs 
        };
      });
      
      const payload = { 
        facture: { 
          fichier_source: file?.name || 'Saisie Manuelle', 
          date_facture: meta.date || null, 
          devise: meta.currency || 'TND', 
          id_concession: concessionId, 
          total_montant: 0 
        }, 
        items_data: itemsData 
      };
      
      await apiCall('POST', '/facture', payload, { force: forceOverwrite });
      alert('✅ Facture enregistrée avec succès !');
      setExtraction(null); 
      setFile(null);
    } catch (e) { 
      console.error(e);
      alert("❌ Erreur lors de la sauvegarde."); 
    } finally { 
      setLoading(false); 
    }
  };

  const addColumn = () => {
    const colName = prompt('Nom de la nouvelle colonne :');
    if (!colName || !tabulatorInst.current) return;
    
    const safeField = colName.trim().replace(/[^a-zA-Z0-9_]/g, "_");
    tabulatorInst.current.addColumn({
      title: colName.trim(),
      field: safeField,
      editor: "input",
      minWidth: 140
    });
  };

  const addRow = () => {
    if (!tabulatorInst.current) return;
    tabulatorInst.current.addRow({ description: "" }, true);
  };

  return (
    <div className="space-y-6 max-w-full mx-auto px-4">
      <h2 className="text-3xl font-bold flex items-center gap-3 text-violet-900 dark:text-white">
        <UploadCloud className="text-primaryLight dark:text-primaryDark"/> Déposer une facture
      </h2>
      
      {!extraction ? (
        // ... (partie upload inchangée)
        <div className="bg-white dark:bg-[#1a233a] border border-violet-200 dark:border-[#2e3b5e] p-12 rounded-2xl shadow-sm">
          <div className="max-w-md mx-auto text-center space-y-6">
            <div className="flex items-center justify-center gap-4">
              <label className="bg-primaryLight/10 text-primaryLight dark:bg-primaryDark/20 dark:text-primaryDark px-6 py-2 rounded-lg font-semibold cursor-pointer hover:bg-primaryLight/20 transition">
                Choisir un fichier
                <input type="file" onChange={(e) => setFile(e.target.files[0])} className="hidden" />
              </label>
              <span className="text-sm text-slate-500 dark:text-slate-400">
                {file ? file.name : "Aucun fichier choisi"}
              </span>
            </div>
            
            <button 
              onClick={handleExtract} 
              disabled={!file || loading}
              className="w-full bg-primaryLight dark:bg-[#2546a9] text-white px-8 py-4 rounded-xl font-bold transition hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? 'Analyse en cours...' : 'Lancer l\'analyse IA'}
            </button>
          </div>
        </div>
      ) : (
        // ... reste du JSX identique à ton code
        <div className="bg-white dark:bg-[#151c2f] border border-violet-200 dark:border-[#263351] p-6 rounded-2xl shadow-sm">
          <h3 className="text-xl font-bold text-primaryLight dark:text-primaryDark flex items-center gap-2 mb-6">
            <CheckCircle/> Détails du document
          </h3>
          
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
            {/* Concession, Fournisseur, Date - identique à ton code */}
            <div className="md:col-span-1">
              <label className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-2 block">Concession</label>
              <div className="flex gap-2">
                <select value={concessionId} onChange={(e) => setConcessionId(e.target.value)} className="w-full bg-violet-50 dark:bg-[#1e2943] border border-violet-200 dark:border-[#2e3b5e] p-2.5 rounded-lg outline-none focus:border-primaryLight dark:text-white">
                  <option value="">-- Choisir --</option>
                  {concessions.map(c => <option key={c.id_concession} value={c.id_concession}>{c.nom}</option>)}
                </select>
                <div className="flex">
                  <input type="text" placeholder="Nouveau..." value={newConcessionName} onChange={e => setNewConcessionName(e.target.value)} className="w-24 bg-violet-50 dark:bg-[#1e2943] border border-violet-200 dark:border-[#2e3b5e] p-2.5 rounded-l-lg outline-none focus:border-primaryLight dark:text-white"/>
                  <button onClick={handleCreateConcession} className="bg-slate-600 hover:bg-slate-700 text-white px-3 rounded-r-lg transition">Créer</button>
                </div>
              </div>
            </div>

            <div className="md:col-span-1">
              <label className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-2 block">Fournisseur</label>
              <input type="text" value={meta.fournisseur} onChange={e=>setMeta({...meta, fournisseur: e.target.value})} placeholder="Nom du fournisseur" className="w-full bg-violet-50 dark:bg-[#1e2943] border border-violet-200 dark:border-[#2e3b5e] p-2.5 rounded-lg outline-none focus:border-primaryLight dark:text-white" />
            </div>

            <div className="md:col-span-1">
              <label className="text-xs font-bold text-slate-500 uppercase tracking-wider mb-2 block">Date de la facture</label>
              <input type="date" value={meta.date} onChange={e=>setMeta({...meta, date: e.target.value})} className="w-full bg-violet-50 dark:bg-[#1e2943] border border-violet-200 dark:border-[#2e3b5e] p-2.5 rounded-lg outline-none focus:border-primaryLight dark:text-white" />
            </div>
          </div>

          <h3 className="font-bold text-slate-800 dark:text-white mb-4">Articles extraits</h3>
          
          <div className="w-full rounded-2xl overflow-hidden border border-slate-700 bg-[#0f172a]">
            <div className="overflow-x-auto">
              <div ref={tableRef} className="min-w-[1000px]" />
            </div>
          </div>
          
          <div className="flex flex-wrap justify-between items-center gap-4 mt-4 mb-8">
            <button onClick={() => tabulatorInst.current?.download("csv", "facture.csv")} className="text-sm bg-violet-100 text-violet-800 dark:bg-[#1e2943] dark:text-slate-300 px-4 py-2 rounded-lg flex items-center gap-2 hover:bg-violet-200 dark:hover:bg-[#2e3b5e] transition border border-violet-200 dark:border-[#2e3b5e]">
              <Download size={16}/> Exporter CSV
            </button>

            <div className="flex gap-2">
              <button onClick={addColumn} className="text-sm bg-white dark:bg-[#1e2943] text-slate-700 dark:text-slate-300 px-4 py-2 rounded-lg flex items-center gap-2 hover:bg-slate-50 dark:hover:bg-[#2e3b5e] transition border border-violet-200 dark:border-[#2e3b5e]">
                <Columns size={16}/> + Colonne
              </button>
              <button onClick={addRow} className="text-sm bg-white dark:bg-[#1e2943] text-slate-700 dark:text-slate-300 px-4 py-2 rounded-lg flex items-center gap-2 hover:bg-slate-50 dark:hover:bg-[#2e3b5e] transition border border-violet-200 dark:border-[#2e3b5e]">
                <Plus size={16}/> + Ligne
              </button>
            </div>
          </div>
          
          <div className="flex flex-col sm:flex-row justify-between items-center bg-violet-50 dark:bg-[#1e2943] p-5 rounded-xl border border-violet-100 dark:border-[#2e3b5e]">
            <label className="flex items-center gap-3 text-sm font-medium text-slate-700 dark:text-slate-300 cursor-pointer mb-4 sm:mb-0">
              <input type="checkbox" checked={forceOverwrite} onChange={e => setForceOverwrite(e.target.checked)} className="w-4 h-4 rounded border-slate-300 text-primaryLight focus:ring-primaryLight"/> 
              Écraser si existante
            </label>
            <button onClick={saveFacture} disabled={loading} className="w-full sm:w-auto bg-primaryLight dark:bg-primaryDark hover:opacity-90 text-white px-8 py-3 rounded-lg font-bold flex items-center justify-center gap-2 transition shadow-md">
              <Save size={18}/> Enregistrer dans la base
            </button>
          </div>
        </div>
      )}
    </div>
  );
}