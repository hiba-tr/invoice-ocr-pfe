// frontend/src/components/ResumeModal.jsx
import { useState, useEffect } from 'react';
import { X, FileText, Calendar, Building2, Package, Euro, TrendingUp, AlertCircle, Landmark } from 'lucide-react';
import { apiCall } from '../api/api';

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
        const resumeData = await apiCall('POST', `/facture/${factureId}/resume`);
        const factureDataRaw = await apiCall('GET', `/facture/${factureId}`);
        
        console.log('📊 Facture data raw:', factureDataRaw);
        console.log('📊 Resume data:', resumeData);
        
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
  const nbArticles = resume?.nb_articles || 0;
  let totalTtc = resume?.total_ttc || 0;
  if (totalTtc === 0 && resume?.total_ht) totalTtc = resume.total_ht;
  
  // 🔥 CORRECTION : Extraire correctement la concession
  // Priorité 1: depuis factureInfo.concession (objet)
  // Priorité 2: depuis factureInfo.concession_nom (string)
  // Priorité 3: depuis factureData.concession
  // Priorité 4: depuis resume.concession
  // Priorité 5: depuis le texte du résumé (fallback)
  let concession = "Non spécifiée";
  
  if (factureInfo?.concession) {
    if (typeof factureInfo.concession === 'object' && factureInfo.concession.nom) {
      concession = factureInfo.concession.nom;
    } else if (typeof factureInfo.concession === 'string') {
      concession = factureInfo.concession;
    }
  } else if (factureInfo?.concession_nom && typeof factureInfo.concession_nom === 'string') {
    concession = factureInfo.concession_nom;
  } else if (factureData?.concession && typeof factureData.concession === 'string') {
    concession = factureData.concession;
  } else if (resume?.concession && typeof resume.concession === 'string') {
    concession = resume.concession;
  }
  
  // 🔥 Extraire le fournisseur correctement
  let fournisseur = "Non spécifié";
  if (factureInfo?.fournisseur && typeof factureInfo.fournisseur === 'string') {
    fournisseur = factureInfo.fournisseur;
  } else if (factureData?.fournisseur && typeof factureData.fournisseur === 'string') {
    fournisseur = factureData.fournisseur;
  } else if (resume?.fournisseur && typeof resume.fournisseur === 'string') {
    fournisseur = resume.fournisseur;
  }
  
  const dateEmission = factureInfo?.date_facture || resume?.date_emission || "N/A";
  const formattedDate = dateEmission !== "N/A" ? dateEmission.split('T')[0] : "N/A";
  const devise = factureInfo?.devise || resume?.devise || "EUR";

  console.log('🔄 Concession extraite:', concession);
  console.log('🔄 Fournisseur extrait:', fournisseur);

  return (
    <div 
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="glass-card w-full max-w-3xl max-h-[85vh] overflow-hidden flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-slate-200/50">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full flex items-center justify-center" style={{ backgroundColor: `${primaryColor}20` }}>
              <FileText size={20} style={{ color: primaryColor }} />
            </div>
            <div>
              <h3 className="font-display text-xl font-bold text-slate-800">Résumé intelligent</h3>
              <p className="text-xs text-slate-500">Facture #{factureId}</p>
            </div>
          </div>
          <button onClick={onClose} className="p-2 rounded-lg hover:bg-slate-100 transition-colors">
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
              <div className="bg-gradient-to-r from-cyan-50 to-blue-50 rounded-xl p-6 border-l-4" style={{ borderLeftColor: primaryColor }}>
                <p className="text-slate-700">{resume.resume_texte || "Aucun résumé disponible"}</p>
              </div>

              {/* Statistiques */}
              <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
                <div className="glass-card text-center py-3">
                  <Package size={18} className="mx-auto mb-1 text-slate-400" />
                  <p className="text-2xl font-bold text-slate-800">{nbArticles}</p>
                  <p className="text-xs text-slate-500">Articles</p>
                </div>
                <div className="glass-card text-center py-3">
                  <Euro size={18} className="mx-auto mb-1 text-slate-400" />
                  <p className="text-xl font-bold truncate" style={{ color: primaryColor }}>{totalTtc.toLocaleString('fr-FR')}</p>
                  <p className="text-xs text-slate-500">Total TTC ({devise})</p>
                </div>
                <div className="glass-card text-center py-3">
                  <Building2 size={18} className="mx-auto mb-1 text-slate-400" />
                  <p className="text-sm font-medium text-slate-800 truncate" title={fournisseur}>
                    {fournisseur.length > 15 ? fournisseur.substring(0,15)+'...' : fournisseur}
                  </p>
                  <p className="text-xs text-slate-500">Fournisseur</p>
                </div>
                <div className="glass-card text-center py-3">
                  <Landmark size={18} className="mx-auto mb-1 text-slate-400" />
                  {/* 🔥 CORRECTION : Afficher la concession correctement */}
                  <p className="text-sm font-medium text-slate-800 truncate" title={concession}>
                    {concession.length > 15 ? concession.substring(0,15)+'...' : concession}
                  </p>
                  <p className="text-xs text-slate-500">Concession</p>
                </div>
                <div className="glass-card text-center py-3">
                  <Calendar size={18} className="mx-auto mb-1 text-slate-400" />
                  <p className="text-sm font-medium text-slate-800">{formattedDate}</p>
                  <p className="text-xs text-slate-500">Date</p>
                </div>
              </div>

              {/* Catégories */}
              {resume.categories_principales?.length > 0 && (
                <div className="glass-card p-4">
                  <h4 className="font-medium text-slate-800 mb-3 flex items-center gap-2">
                    <TrendingUp size={16} style={{ color: primaryColor }} />
                    Catégories principales
                  </h4>
                  <div className="flex flex-wrap gap-2">
                    {resume.categories_principales.map((cat, idx) => (
                      <span key={idx} className="px-3 py-1 rounded-full text-xs font-mono" style={{ backgroundColor: `${primaryColor}15`, color: primaryColor }}>
                        {cat}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Détail des items */}
              {resume.details_items?.length > 0 && (
                <div className="glass-card p-4">
                  <h4 className="font-medium text-slate-800 mb-3">Détail des articles</h4>
                  <div className="space-y-2 max-h-60 overflow-y-auto">
                    {resume.details_items.map((item, idx) => (
                      <div key={idx} className="flex justify-between items-center py-2 border-b border-slate-100 last:border-0">
                        <span className="text-sm text-slate-700">{item.description}</span>
                        <div className="flex gap-3">
                          {Object.entries(item.valeurs || {}).map(([key, val]) => (
                            <span key={key} className="text-xs font-mono text-slate-500">
                              {key}: {String(val)}
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
        <div className="p-6 border-t border-slate-200/50 flex justify-end">
          <button onClick={onClose} className="btn-glass px-6">
            Fermer
          </button>
        </div>
      </div>
    </div>
  );
}