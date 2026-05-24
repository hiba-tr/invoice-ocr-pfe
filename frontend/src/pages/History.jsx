// History.jsx - Version complètement corrigée
import { useState, useEffect, useCallback } from 'react';
import { useApp } from '../context/AppContext';
import { apiCall } from '../api/api';
import { Trash2, ChevronDown, Bot, FileText, Clock } from 'lucide-react';
import ResumeModal from "../components/ResumeModal";

const calculateTotalFromSections = (sections) => {
  let total = 0;
  const totalKeywords = ['total', 'montant', 'amount', 'total ttc', 'total ht', 'total général', 'total facture'];
  sections.forEach(section => {
    const headers = section.headers || [];
    const rows = section.items_data || [];
    let totalColIndex = headers.findIndex(h => totalKeywords.some(kw => h.toLowerCase().includes(kw)));
    if (totalColIndex === -1) {
      totalColIndex = headers.findIndex(h => /(total|montant|amount|prix)/i.test(h));
    }
    rows.forEach(row => {
      if (totalColIndex >= 0) {
        const headerName = headers[totalColIndex];
        const val = row.valeurs?.[headerName] || row[headerName];
        if (val) {
          const num = parseFloat(String(val).replace(',', '.'));
          if (!isNaN(num)) total += num;
        }
      }
    });
  });
  return total;
};

export default function History() {
  const { showSpinner, hideSpinner, showToast } = useApp();
  const [factures, setFactures] = useState([]);
  const [expandedId, setExpandedId] = useState(null);
  const [details, setDetails] = useState({});
  const [loadingDetails, setLoadingDetails] = useState({});
  const [selectedFactureId, setSelectedFactureId] = useState(null);
  const [showResumeModal, setShowResumeModal] = useState(false);

  // Chargement initial des factures (rapide)
  useEffect(() => {
    const loadHistory = async () => {
      showSpinner();
      try {
        const res = await apiCall('GET', '/factures');
        setFactures(res);
      } catch {
        showToast("Erreur lors du chargement de l'historique", 'danger');
      } finally {
        hideSpinner();
      }
    };
    loadHistory();
  }, [showSpinner, hideSpinner, showToast]);

  // Chargement des détails uniquement quand on développe (chargement progressif)
  const loadDetails = useCallback(async (factureId) => {
    if (details[factureId]) return;
    
    setLoadingDetails(prev => ({ ...prev, [factureId]: true }));
    try {
      const sectionsData = await apiCall('GET', `/facture/${factureId}/sections`);
      const sections = sectionsData?.sections || [];
      setDetails(prev => ({ ...prev, [factureId]: sections }));
    } catch (error) {
      console.error('Erreur chargement détails:', error);
      setDetails(prev => ({ ...prev, [factureId]: [] }));
    } finally {
      setLoadingDetails(prev => ({ ...prev, [factureId]: false }));
    }
  }, [details]);

  const handleToggleExpand = (factureId) => {
    if (expandedId === factureId) {
      setExpandedId(null);
    } else {
      setExpandedId(factureId);
      loadDetails(factureId);
    }
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Supprimer cette facture ?')) return;
    showSpinner();
    try {
      await apiCall('DELETE', `/facture/${id}`);
      setFactures(prev => prev.filter(f => f.id_facture !== id));
      setDetails(prev => {
        const newDetails = { ...prev };
        delete newDetails[id];
        return newDetails;
      });
      showToast('Facture supprimée', 'success');
    } catch {
      showToast('Erreur suppression', 'danger');
    } finally {
      hideSpinner();
    }
  };

  const handleOpenResume = (id) => {
    setSelectedFactureId(id);
    setShowResumeModal(true);
  };

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
        <Clock size={24} className="text-primary-light dark:text-primary-dark" />
        Historique des factures
      </h2>

      {factures.map((f) => {
        const detList = details[f.id_facture] || [];
        const isLoading = loadingDetails[f.id_facture];
        const isExpanded = expandedId === f.id_facture;

        return (
          <div key={f.id_facture} className="glass-card overflow-hidden">
            {/* Header */}
            <div
              className="flex items-center justify-between cursor-pointer p-4 hover:bg-white/30 dark:hover:bg-white/5 transition-colors"
              onClick={() => handleToggleExpand(f.id_facture)}
            >
              <div className="flex items-center gap-4 flex-wrap">
                <span className="font-display font-bold text-lg text-primary-light dark:text-primary-dark">
                  #{f.id_facture}
                </span>
                <span className="text-sm text-slate-500 dark:text-slate-400">
                  {f.date_facture?.split('T')[0] || 'N/A'}
                </span>
                <span className="badge-status bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 text-xs">
                  {detList.length} section(s)
                </span>
                {f.fichier_source && (
                  <span className="text-xs text-slate-400 dark:text-slate-500 truncate max-w-[200px]">
                    📄 {f.fichier_source}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-4">
                <span className="font-bold text-slate-700 dark:text-slate-200">
                  {(f.total_montant || 0).toFixed(2)} {f.devise || '€'}
                </span>
                <ChevronDown
                  size={20}
                  className={`text-slate-400 transition-transform duration-200 ${isExpanded ? 'rotate-180' : ''}`}
                />
              </div>
            </div>

            {/* Contenu expandable */}
            {isExpanded && (
              <div className="mt-4 pt-4 border-t border-slate-200/50 dark:border-slate-700/30">
                {/* Métadonnées */}
                <div className="mb-4 p-4 bg-gradient-to-br from-blue-50/60 to-cyan-50/40 dark:from-blue-900/20 dark:to-cyan-900/10 rounded-xl">
                  <h4 className="text-sm font-semibold text-blue-800 dark:text-blue-300 mb-3 flex items-center gap-2">
                    📋 Métadonnées
                  </h4>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                    <div>
                      <span className="text-xs text-slate-500 uppercase tracking-wider">Date</span>
                      <p className="font-medium text-slate-800 dark:text-slate-200">
                        {f.date_facture ? new Date(f.date_facture).toLocaleDateString('fr-FR') : '—'}
                      </p>
                    </div>
                    <div>
                      <span className="text-xs text-slate-500 uppercase tracking-wider">Concession</span>
                      <p className="font-medium text-slate-800 dark:text-slate-200">
                        {f.concession?.nom || '—'}
                      </p>
                    </div>
                    <div>
                      <span className="text-xs text-slate-500 uppercase tracking-wider">Fournisseur</span>
                      <p className="font-medium text-slate-800 dark:text-slate-200 truncate">
                        {f.fournisseur || '—'}
                      </p>
                    </div>
                    <div>
                      <span className="text-xs text-slate-500 uppercase tracking-wider">Devise</span>
                      <p className="font-medium text-slate-800 dark:text-slate-200">
                        {f.devise || 'EUR'}
                      </p>
                    </div>
                  </div>

                  {/* extra_metadata */}
                  {f.extra_metadata && (() => {
                    try {
                      const parsed = JSON.parse(f.extra_metadata);
                      const infos = Array.isArray(parsed) ? parsed : [String(parsed)];
                      if (infos.length === 0) return null;
                      return (
                        <div className="mt-3 pt-2 border-t border-blue-100 dark:border-blue-800/20">
                          <span className="text-xs text-slate-500 uppercase tracking-wider">Infos complémentaires</span>
                          <ul className="mt-1 space-y-1">
                            {infos.map((info, idx) => (
                              <li key={idx} className="text-sm text-slate-700 dark:text-slate-300 flex items-center gap-1">
                                <span className="text-blue-400">•</span> {info}
                              </li>
                            ))}
                          </ul>
                        </div>
                      );
                    } catch (e) {
                      return (
                        <div className="mt-3 pt-2 border-t border-blue-100 dark:border-blue-800/20">
                          <span className="text-xs text-slate-500 uppercase tracking-wider">Infos complémentaires</span>
                          <p className="text-sm text-slate-700 dark:text-slate-300 mt-1">{f.extra_metadata}</p>
                        </div>
                      );
                    }
                  })()}
                </div>

                {/* Actions */}
                <div className="flex justify-end gap-2 mb-4">
                  <button
                    onClick={(e) => { 
                      e.stopPropagation(); 
                      handleOpenResume(f.id_facture); 
                    }}
                    className="btn-glass text-blue-600 dark:text-blue-400 text-sm"
                  >
                    <Bot size={16} /> Résumé IA
                  </button>
                  <button
                    onClick={(e) => { 
                      e.stopPropagation(); 
                      handleDelete(f.id_facture); 
                    }}
                    className="btn-glass text-red-600 dark:text-red-400 text-sm"
                  >
                    <Trash2 size={16} /> Supprimer
                  </button>
                </div>

                {/* Sections avec leurs valeurs */}
                {isLoading ? (
                  <div className="flex justify-center py-8">
                    <div className="animate-spin rounded-full h-6 w-6 border-2 border-t-transparent border-cyan-500" />
                    <span className="ml-2 text-slate-500">Chargement des détails...</span>
                  </div>
                ) : detList.length > 0 ? (
                  detList.map((section, idx) => {
                    const headers = section.headers || [];
                    const rows = section.items_data || [];
                    if (headers.length === 0 || rows.length === 0) return null;

                    return (
                      <div key={idx} className="mb-6">
                        <h4 className="font-display font-bold text-sm text-slate-700 dark:text-slate-300 mb-2">
                          {section.titre || `Tableau ${idx + 1}`}
                        </h4>
                        <div className="overflow-x-auto rounded-xl border border-slate-200/30 dark:border-slate-700/30">
                          <table className="w-full text-sm">
                            <thead>
                              <tr className="bg-gradient-to-r from-blue-50/80 to-cyan-50/80 dark:from-blue-950/30 dark:to-cyan-950/20">
                                {headers.map((col) => (
                                  <th key={col} className="px-4 py-3 text-left font-mono text-xs uppercase tracking-wider text-blue-700 dark:text-cyan-400 whitespace-nowrap">
                                    {col}
                                  </th>
                                ))}
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-blue-100/50 dark:divide-slate-800/50">
                              {rows.map((row, i) => {
                                const isDescCol = /(designation|description|libelle|article|item)/i.test(headers[0] || '');
                                return (
                                  <tr key={i} className="hover:bg-blue-50/30 dark:hover:bg-slate-800/30 transition-colors">
                                    {headers.map((col) => {
                                      const isNumeric = /(qte|quantité|quantity|prix|tarif|total|montant|amount|taux)/i.test(col);
                                      let value = '—';
                                      
                                      if (isDescCol && col === headers[0]) {
                                        value = row.description || row.valeurs?.[col] || '—';
                                      } else {
                                        value = row.valeurs?.[col] || row[col] || '—';
                                      }
                                      
                                      return (
                                        <td 
                                          key={col} 
                                          className={`px-4 py-3 whitespace-nowrap ${
                                            isDescCol && col === headers[0] 
                                              ? 'font-medium text-slate-800 dark:text-slate-200' 
                                              : isNumeric 
                                                ? 'font-mono text-right text-slate-600 dark:text-slate-400' 
                                                : 'text-slate-600 dark:text-slate-400'
                                          }`}
                                        >
                                          {value}
                                        </td>
                                      );
                                    })}
                                  </tr>
                                );
                              })}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    );
                  })
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

      {showResumeModal && (
        <ResumeModal
          isOpen={showResumeModal}
          onClose={() => {
            setShowResumeModal(false);
            setSelectedFactureId(null);
          }}
          factureId={selectedFactureId}
          factureData={factures.find((f) => f.id_facture === selectedFactureId)}
        />
      )}
    </div>
  );
}