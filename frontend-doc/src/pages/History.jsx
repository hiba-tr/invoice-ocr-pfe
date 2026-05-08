import { useState, useEffect } from 'react';
import { apiCall } from '../api/api';
import { Trash2, ChevronDown, Bot } from 'lucide-react';

export default function History() {
  const [factures, setFactures] = useState([]);
  const [expandedId, setExpandedId] = useState(null);
  const [details, setDetails] = useState({});

  // Correction : La fonction est définie et appelée directement dans le useEffect
  useEffect(() => {
    const loadHistory = async () => {
      try {
        const res = await apiCall('GET', '/factures');
        setFactures(res);
        
        const detailsPromises = res.map(f => apiCall('GET', `/facture/${f.id_facture}/details`));
        const allDetails = await Promise.all(detailsPromises);
        const detMap = {};
        res.forEach((f, i) => detMap[f.id_facture] = allDetails[i].details);
        setDetails(detMap);
      } catch (e) { 
        console.error("Erreur lors du chargement de l'historique :", e); // 'e' est utilisé
      }
    };

    loadHistory();
  }, []);

  const handleDelete = async (id) => {
    if (!window.confirm('Supprimer cette facture ?')) return;
    try {
      await apiCall('DELETE', `/facture/${id}`);
      // Rechargement manuel de la liste après suppression
      const res = await apiCall('GET', '/factures');
      setFactures(res);
    } catch (e) {
      console.error("Erreur lors de la suppression :", e); // 'e' est utilisé
    }
  };

  const handleResumeIA = async (id) => {
    try {
      const res = await apiCall('POST', `/facture/${id}/resume`);
      alert(res.resume?.resume_texte || 'Aucun résumé disponible.');
    } catch (e) { 
      console.error("Erreur lors du résumé IA :", e); // 'e' est utilisé
      alert("Erreur résumé IA"); 
    }
  };

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold text-slate-800 dark:text-white">Historique</h2>
      <div className="space-y-3">
        {factures.map(f => (
          <div key={f.id_facture} className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl overflow-hidden shadow-sm">
            <div className="p-4 flex items-center justify-between cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors" onClick={() => setExpandedId(expandedId === f.id_facture ? null : f.id_facture)}>
                <div className="flex gap-4 items-center">
                    <span className="font-bold text-primary dark:text-cyan">#{f.id_facture}</span>
                    <span className="text-slate-600 dark:text-slate-300">{f.date_facture || 'N/A'}</span>
                    <span className="bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 px-3 py-1 rounded-full text-xs border border-slate-200 dark:border-slate-700">
                      Concession: {f.id_concession}
                    </span>
                </div>
                <div className="flex items-center gap-4 text-slate-700 dark:text-slate-200">
                    <span className="font-bold">{parseFloat(f.total_montant || 0).toFixed(2)} €</span>
                    <ChevronDown size={18} className={`transition-transform duration-200 ${expandedId === f.id_facture ? 'rotate-180' : ''}`}/>
                </div>
            </div>
            
            {expandedId === f.id_facture && (
                <div className="p-4 border-t border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950/50">
                    <div className="flex justify-end gap-2 mb-4">
                        <button onClick={() => handleResumeIA(f.id_facture)} className="text-sm bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300 hover:bg-blue-200 dark:hover:bg-blue-900/50 px-3 py-1.5 rounded flex items-center gap-2 transition-colors"><Bot size={16}/> Résumé IA</button>
                        <button onClick={() => handleDelete(f.id_facture)} className="text-sm bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300 hover:bg-red-200 dark:hover:bg-red-900/50 px-3 py-1.5 rounded flex items-center gap-2 transition-colors"><Trash2 size={16}/> Supprimer</button>
                    </div>
                    <div className="text-sm rounded-lg border border-slate-200 dark:border-slate-800 overflow-hidden bg-white dark:bg-slate-900">
                        {details[f.id_facture]?.map((d, i) => (
                            <div key={i} className="flex justify-between border-b border-slate-100 dark:border-slate-800/50 py-3 px-4 last:border-0 hover:bg-slate-50 dark:hover:bg-slate-800/30">
                                <span className="font-medium text-slate-700 dark:text-slate-300">{d.item}</span>
                                <span className="font-mono text-slate-500 dark:text-slate-400 bg-slate-100 dark:bg-slate-950 px-2 py-0.5 rounded">{d.colonne}: {d.valeur}</span>
                            </div>
                        ))}
                    </div>
                </div>
            )}
          </div>
        ))}
        {factures.length === 0 && (
          <div className="text-center p-8 text-slate-500 dark:text-slate-400 bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800">
            Aucune facture enregistrée dans l'historique.
          </div>
        )}
      </div>
    </div>
  );
}