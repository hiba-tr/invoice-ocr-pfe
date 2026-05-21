import { useState, useEffect } from 'react';
import { X, FileText, Calendar, Building2, Package, Euro, TrendingUp, AlertCircle, Landmark } from 'lucide-react';

export default function ResumeModal({ isOpen, onClose, factureId, factureData }) {
  const [resume, setResume] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [factureInfo, setFactureInfo] = useState(null);

  useEffect(() => {
    if (!isOpen || !factureId) return;

    const fetchData = async () => {
      setLoading(true);
      setError(null);
      try {
        // 1. Récupérer le résumé
        const resumeResponse = await fetch(`http://localhost:8000/facture/${factureId}/resume`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' }
        });
        const resumeData = await resumeResponse.json();
        
        // 2. Récupérer les informations de la facture (concession, fournisseur)
        const factureResponse = await fetch(`http://localhost:8000/facture/${factureId}`);
        const factureDataRaw = await factureResponse.json();
        
        console.log("📊 Facture data:", factureDataRaw);
        console.log("📊 Resume data:", resumeData);
        
        setFactureInfo(factureDataRaw.facture || factureDataRaw);
        setResume(resumeData.resume || resumeData);
      } catch (err) {
        console.error("Erreur fetch:", err);
        setError("Impossible de charger le résumé");
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, [isOpen, factureId]);

  if (!isOpen) return null;

  const primaryColor = '#06b6d4';

  // Récupération des valeurs depuis factureInfo (base de données)
  const nbArticles = resume?.nb_articles || 0;
  
  // Total TTC
  let totalTtc = resume?.total_ttc || 0;
  if (totalTtc === 0 && resume?.total_ht) {
    totalTtc = resume.total_ht;
  }
  
  // ✅ Fournisseur - depuis la base (factureInfo)
  const fournisseur = factureInfo?.fournisseur || 
                      factureData?.fournisseur || 
                      "Non spécifié";
  
  // ✅ Concession - depuis la base (factureInfo.concession)
  const concession = factureInfo?.concession?.nom || 
                     factureInfo?.concession_nom ||
                     factureData?.concession ||
                     "Non spécifiée";
  
  // Date
  const dateEmission = factureInfo?.date_facture || 
                       resume?.date_emission || 
                       "N/A";
  const formattedDate = dateEmission !== "N/A" ? dateEmission.split('T')[0] : "N/A";
  
  // Devise
  const devise = factureInfo?.devise || resume?.devise || "EUR";

  console.log("🔄 Affichage modal:", { 
    nbArticles, totalTtc, fournisseur, concession, formattedDate,
    factureInfo 
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm animate-fade-in">
      <div className="glass-card w-full max-w-3xl max-h-[85vh] overflow-hidden flex flex-col animate-slide-up">
        
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-slate-200/50 dark:border-slate-700/30">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full flex items-center justify-center" style={{ backgroundColor: `${primaryColor}20` }}>
              <FileText size={20} style={{ color: primaryColor }} />
            </div>
            <div>
              <h3 className="font-display text-xl font-bold text-slate-800 dark:text-white">
                Résumé intelligent
              </h3>
              <p className="text-xs text-slate-500 dark:text-slate-400">
                Facture #{factureId}
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
          >
            <X size={20} className="text-slate-500" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <div className="animate-spin rounded-full h-8 w-8 border-2 border-t-transparent" style={{ borderColor: primaryColor }} />
              <span className="ml-3 text-slate-500">Génération du résumé...</span>
            </div>
          ) : error ? (
            <div className="text-center py-12 text-red-500">
              <AlertCircle size={48} className="mx-auto mb-4" />
              <p>{error}</p>
            </div>
          ) : resume ? (
            <>
              {/* Résumé texte */}
              <div className="bg-gradient-to-r from-cyan-50/50 to-blue-50/50 dark:from-cyan-950/20 dark:to-blue-950/20 rounded-xl p-6 border-l-4" style={{ borderLeftColor: primaryColor }}>
                <p className="text-slate-700 dark:text-slate-300 leading-relaxed">
                  {resume.resume_texte || "Aucun résumé disponible"}
                </p>
              </div>

              {/* Statistiques - 5 cartes avec les données de la base */}
              <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
                <div className="glass-card text-center py-3">
                  <Package size={18} className="mx-auto mb-1 text-slate-400" />
                  <p className="text-2xl font-bold text-slate-800 dark:text-white">{nbArticles}</p>
                  <p className="text-xs text-slate-500">Articles</p>
                </div>
                <div className="glass-card text-center py-3">
                  <Euro size={18} className="mx-auto mb-1 text-slate-400" />
                  <p className="text-xl font-bold truncate" style={{ color: primaryColor }}>
                    {totalTtc.toLocaleString('fr-FR')}
                  </p>
                  <p className="text-xs text-slate-500">Total TTC ({devise})</p>
                </div>
                <div className="glass-card text-center py-3">
                  <Building2 size={18} className="mx-auto mb-1 text-slate-400" />
                  <p className="text-sm font-medium text-slate-800 dark:text-white truncate" title={fournisseur}>
                    {fournisseur.length > 15 ? fournisseur.substring(0, 15) + '...' : fournisseur}
                  </p>
                  <p className="text-xs text-slate-500">Fournisseur</p>
                </div>
                <div className="glass-card text-center py-3">
                  <Landmark size={18} className="mx-auto mb-1 text-slate-400" />
                  <p className="text-sm font-medium text-slate-800 dark:text-white truncate" title={concession}>
                    {concession.length > 15 ? concession.substring(0, 15) + '...' : concession}
                  </p>
                  <p className="text-xs text-slate-500">Concession</p>
                </div>
                <div className="glass-card text-center py-3">
                  <Calendar size={18} className="mx-auto mb-1 text-slate-400" />
                  <p className="text-sm font-medium text-slate-800 dark:text-white">
                    {formattedDate}
                  </p>
                  <p className="text-xs text-slate-500">Date</p>
                </div>
              </div>

              {/* Catégories */}
              {resume.categories_principales?.length > 0 && (
                <div className="glass-card p-4">
                  <h4 className="font-medium text-slate-800 dark:text-white mb-3 flex items-center gap-2">
                    <TrendingUp size={16} style={{ color: primaryColor }} />
                    Catégories principales
                  </h4>
                  <div className="flex flex-wrap gap-2">
                    {resume.categories_principales.map((cat, idx) => (
                      <span
                        key={idx}
                        className="px-3 py-1 rounded-full text-xs font-mono"
                        style={{ backgroundColor: `${primaryColor}15`, color: primaryColor }}
                      >
                        {cat}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Détail des items */}
              {resume.details_items?.length > 0 && (
                <div className="glass-card p-4">
                  <h4 className="font-medium text-slate-800 dark:text-white mb-3">Détail des articles</h4>
                  <div className="space-y-2 max-h-60 overflow-y-auto">
                    {resume.details_items.map((item, idx) => (
                      <div key={idx} className="flex justify-between items-center py-2 border-b border-slate-100 dark:border-slate-700/50 last:border-0">
                        <span className="text-sm text-slate-700 dark:text-slate-300">{item.description}</span>
                        <div className="flex gap-3">
                          {Object.entries(item.valeurs).map(([key, val]) => (
                            <span key={key} className="text-xs font-mono text-slate-500">
                              {key}: {val}
                            </span>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          ) : (
            <div className="text-center py-12 text-slate-500">
              <p>Aucune donnée disponible</p>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="p-6 border-t border-slate-200/50 dark:border-slate-700/30 flex justify-end">
          <button
            onClick={onClose}
            className="btn-glass px-6"
          >
            Fermer
          </button>
        </div>
      </div>
    </div>
  );
}