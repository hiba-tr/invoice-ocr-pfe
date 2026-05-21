import { useState, useEffect } from 'react';
import { useApp } from '../context/AppContext';
import { apiCall } from '../api/api';
import { Trash2, ChevronDown, Bot, FileText, Clock } from 'lucide-react';
import ResumeModal from '../components/ResumeModal';

export default function History() {
  const { showSpinner, hideSpinner, showToast } = useApp();
  const [factures, setFactures] = useState([]);
  const [expandedId, setExpandedId] = useState(null);
  const [details, setDetails] = useState({});
  
  // État pour le modal de résumé
  const [modalOpen, setModalOpen] = useState(false);
  const [selectedFactureId, setSelectedFactureId] = useState(null);
  const [selectedFactureData, setSelectedFactureData] = useState(null);

  useEffect(() => {
    const loadHistory = async () => {
      showSpinner();
      try {
        const res = await apiCall('GET', '/factures');
        setFactures(res);
        const detailsPromises = res.map(f => apiCall('GET', `/facture/${f.id_facture}/details`));
        const allDetails = await Promise.all(detailsPromises);
        const detMap = {};
        res.forEach((f, i) => detMap[f.id_facture] = allDetails[i]?.details || []);
        setDetails(detMap);
      } catch {
        showToast("Erreur lors du chargement de l'historique", 'danger');
      } finally {
        hideSpinner();
      }
    };
    loadHistory();
  }, [hideSpinner, showSpinner, showToast]);

  const handleDelete = async (id) => {
    if (!window.confirm('Supprimer cette facture ?')) return;
    showSpinner();
    try {
      await apiCall('DELETE', `/facture/${id}`);
      setFactures(prev => prev.filter(f => f.id_facture !== id));
      showToast('Facture supprimée', 'success');
    } catch {
      showToast('Erreur suppression', 'danger');
    } finally {
      hideSpinner();
    }
  };

  const handleResumeIA = (id, factureData) => {
    setSelectedFactureId(id);
    setSelectedFactureData(factureData);
    setModalOpen(true);
  };

  const handleCloseModal = () => {
    setModalOpen(false);
    setSelectedFactureId(null);
    setSelectedFactureData(null);
  };

  // Fonction pour reconstruire le tableau à partir des détails
  const buildTableFromDetails = (detList) => {
    if (!detList || detList.length === 0) return { columns: [], rows: [] };

    // Extraire les colonnes uniques (garder le nom original)
    const columnsSet = new Set();
    detList.forEach(d => {
      if (d.colonne) columnsSet.add(d.colonne);
    });
    const columns = ['Article', ...Array.from(columnsSet)];

    // Grouper par item (article)
    const itemMap = {};
    detList.forEach(d => {
      const itemName = d.item || 'Sans nom';
      if (!itemMap[itemName]) {
        itemMap[itemName] = {};
      }
      if (d.colonne) {
        itemMap[itemName][d.colonne] = d.valeur || '—';
      }
    });

    // Construire les lignes
    const rows = Object.entries(itemMap).map(([item, valeurs]) => ({
      Article: item,
      ...valeurs,
    }));

    return { columns, rows };
  };

  const primaryColor = '#06b6d4';

  if (!factures.length) {
    return (
      <div className="max-w-7xl mx-auto text-center py-16 glass-card">
        <FileText size={48} className="mx-auto text-slate-300 dark:text-slate-600 mb-4" />
        <p className="text-slate-500 dark:text-slate-400">Aucune facture enregistrée dans l'historique.</p>
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto space-y-4 animate-fade-in">
      <h2 className="font-display text-2xl font-bold text-slate-800 dark:text-white flex items-center gap-2">
        <Clock size={24} style={{ color: primaryColor }} />
        Historique des factures
      </h2>

      {factures.map(f => {
        const detList = details[f.id_facture] || [];
        const { columns, rows } = buildTableFromDetails(detList);
        const isExpanded = expandedId === f.id_facture;

        return (
          <div key={f.id_facture} className="glass-card overflow-hidden">
            {/* Header cliquable */}
            <div
              className="flex items-center justify-between cursor-pointer p-4 -m-6 mb-0 hover:bg-white/30 dark:hover:bg-white/5 transition-colors"
              onClick={() => setExpandedId(isExpanded ? null : f.id_facture)}
            >
              <div className="flex items-center gap-4 flex-wrap">
                <span className="font-display font-bold text-lg" style={{ color: primaryColor }}>
                  #{f.id_facture}
                </span>
                <span className="text-sm text-slate-500 dark:text-slate-400">
                  {f.date_facture?.split('T')[0] || 'N/A'}
                </span>
                <span className="badge-status bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 text-xs">
                  {detList.length} valeur(s)
                </span>
                {f.fichier_source && (
                  <span className="text-xs text-slate-400 dark:text-slate-500 truncate max-w-[200px]">
                    📄 {f.fichier_source}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-4">
                {(f.total_montant || f.total_montant === 0) && (
                  <span className="font-bold text-slate-700 dark:text-slate-200">
                    {(f.total_montant || 0).toFixed(2)} {f.devise || '€'}
                  </span>
                )}
                <ChevronDown
                  size={20}
                  className={`text-slate-400 transition-transform duration-200 ${isExpanded ? 'rotate-180' : ''}`}
                />
              </div>
            </div>

            {/* Contenu expandable */}
            {isExpanded && (
              <div className="mt-6 pt-6 border-t border-slate-200/50 dark:border-slate-700/30">
                {/* Actions */}
                <div className="flex justify-end gap-2 mb-4">
                  <button
                    onClick={(e) => { 
                      e.stopPropagation(); 
                      handleResumeIA(f.id_facture, f); 
                    }}
                    className="btn-glass text-sm flex items-center gap-1"
                    style={{ color: primaryColor }}
                  >
                    <Bot size={16} /> Résumé IA
                  </button>
                  <button
                    onClick={(e) => { e.stopPropagation(); handleDelete(f.id_facture); }}
                    className="btn-glass text-sm flex items-center gap-1 text-red-600 dark:text-red-400"
                  >
                    <Trash2 size={16} /> Supprimer
                  </button>
                </div>

                {/* Tableau complet */}
                {rows.length > 0 ? (
                  <div className="overflow-x-auto rounded-xl border border-slate-200/30 dark:border-slate-700/30">
                    <table className="w-full text-sm" style={{ minWidth: '100%' }}>
                      <thead>
                        <tr className="bg-gradient-to-r from-blue-50/80 to-cyan-50/80 dark:from-blue-950/30 dark:to-cyan-950/20">
                          {columns.map(col => (
                            <th
                              key={col}
                              className="px-4 py-3 text-left font-mono text-xs uppercase tracking-wider whitespace-nowrap"
                              style={{ color: primaryColor }}
                            >
                              {col}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-blue-100/50 dark:divide-slate-800/50">
                        {rows.map((row, i) => (
                          <tr
                            key={i}
                            className="hover:bg-blue-50/30 dark:hover:bg-slate-800/30 transition-colors"
                          >
                            {columns.map(col => (
                              <td
                                key={col}
                                className={`px-4 py-3 whitespace-nowrap ${
                                  col === 'Article'
                                    ? 'font-medium text-slate-800 dark:text-slate-200'
                                    : 'font-mono text-right text-slate-600 dark:text-slate-400'
                                }`}
                              >
                                {row[col] || '—'}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <p className="text-center text-slate-400 dark:text-slate-500 py-8 italic">
                    Aucune ligne enregistrée pour cette facture.
                  </p>
                )}
              </div>
            )}
          </div>
        );
      })}

      {/* Modal de résumé IA */}
      <ResumeModal
        isOpen={modalOpen}
        onClose={handleCloseModal}
        factureId={selectedFactureId}
        factureData={selectedFactureData}
      />
    </div>
  );
}