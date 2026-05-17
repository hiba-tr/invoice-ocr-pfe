import { useState } from 'react';
import { 
  ShieldCheck, CheckCircle, XCircle, AlertTriangle, 
  ArrowRight, Search, Save, ChevronLeft, Brain
} from 'lucide-react';

export default function SemanticValidation({ 
  items, existingItems,  
  onSave, onBack, forceOverwrite, onForceOverwriteChange 
}) {
  const [decisions, setDecisions] = useState({});
  const [showExistingList, setShowExistingList] = useState({});

  const needsValidation = items.filter(i => i.semantic?.needs_confirmation);
  const autoMatched = items.filter(i => i.semantic?.auto_match && !i.semantic?.needs_confirmation);
  const noMatch = items.filter(i => !i.semantic?.auto_match && !i.semantic?.needs_confirmation);

  const handleDecision = (itemIndex, decision, targetItemId = null) => {
    setDecisions(prev => ({
      ...prev,
      [itemIndex]: { decision, targetItemId }
    }));
  };

  const toggleExistingList = (index) => {
    setShowExistingList(prev => ({
      ...prev,
      [index]: !prev[index]
    }));
  };

  const getConfidenceColor = (score) => {
    if (score >= 0.85) return 'text-emerald-500';
    if (score >= 0.65) return 'text-amber-500';
    return 'text-red-500';
  };

  const getConfidenceBadge = (score) => {
    if (score >= 0.85) return 'badge-success';
    if (score >= 0.65) return 'badge-status badge-warning';
    return 'badge-status badge-danger';
  };

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2 text-xs font-mono uppercase tracking-wider text-purple-500 mb-1">
            <Brain size={14} />
            Validation sémantique
          </div>
          <h2 className="font-display text-2xl font-extrabold text-slate-800 dark:text-white">
            Confirmer les <span className="text-purple-500">correspondances</span>
          </h2>
        </div>
        <div className="flex gap-2">
          <button onClick={onBack} className="btn-glass">
            <ChevronLeft size={16} /> Retour
          </button>
        </div>
      </div>

      {/* Stats KPI */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="glass kpi-card accent-green">
          <span className="text-lg">✅</span>
          <span className="kpi-label">Auto-matchés</span>
          <span className="font-display text-2xl font-bold">{autoMatched.length}</span>
        </div>
        <div className="glass kpi-card accent-amber">
          <span className="text-lg">⚠️</span>
          <span className="kpi-label">À valider</span>
          <span className="font-display text-2xl font-bold">{needsValidation.length}</span>
        </div>
        <div className="glass kpi-card accent-pink">
          <span className="text-lg">🆕</span>
          <span className="kpi-label">Nouveaux items</span>
          <span className="font-display text-2xl font-bold">{noMatch.length}</span>
        </div>
      </div>

      {/* Auto-matched (collapsed) */}
      {autoMatched.length > 0 && (
        <div className="glass-card">
          <h3 className="font-display font-bold text-emerald-600 mb-3 flex items-center gap-2">
            <CheckCircle size={18} />
            Items matchés automatiquement ({autoMatched.length})
          </h3>
          <div className="text-sm text-slate-500 dark:text-slate-400">
            Ces items ont été associés avec une confiance élevée (≥ 85%).
          </div>
        </div>
      )}

      {/* Needs Validation */}
      {needsValidation.length > 0 && (
        <div className="space-y-4">
          <h3 className="font-display font-bold text-amber-600 flex items-center gap-2">
            <AlertTriangle size={18} />
            Items nécessitant une validation ({needsValidation.length})
          </h3>

          {needsValidation.map((item, idx) => (
            <div key={idx} className="glass-card">
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1">
                  <div className="flex items-center gap-3 mb-2">
                    <span className="font-semibold text-slate-800 dark:text-white">
                      {item.description}
                    </span>
                    <span className={`badge-status ${getConfidenceBadge(item.semantic?.suggested_item?.confiance)}`}>
                      {Math.round((item.semantic?.suggested_item?.confiance || 0) * 100)}%
                    </span>
                  </div>

                  {item.semantic?.suggested_item && (
                    <div className="flex items-center gap-2 text-sm text-slate-500 dark:text-slate-400 mb-3">
                      <span>Suggestion :</span>
                      <ArrowRight size={14} />
                      <span className="font-medium text-purple-600 dark:text-purple-400">
                        {item.semantic.suggested_item.libelle}
                      </span>
                    </div>
                  )}

                  <div className="text-xs text-slate-400 mb-3">
                    {item.semantic?.message}
                  </div>

                  {/* Decision buttons */}
                  <div className="flex gap-2 flex-wrap">
                    <button
                      onClick={() => handleDecision(idx, 'accept', item.semantic?.suggested_item?.item_id)}
                      className={`btn-glass text-sm ${
                        decisions[idx]?.decision === 'accept'
                          ? 'bg-emerald-100 dark:bg-emerald-500/20 text-emerald-700 dark:text-emerald-300 border-emerald-300'
                          : ''
                      }`}
                    >
                      <CheckCircle size={14} /> Associer
                    </button>
                    <button
                      onClick={() => handleDecision(idx, 'reject')}
                      className={`btn-glass text-sm ${
                        decisions[idx]?.decision === 'reject'
                          ? 'bg-red-100 dark:bg-red-500/20 text-red-700 dark:text-red-300 border-red-300'
                          : ''
                      }`}
                    >
                      <XCircle size={14} /> Nouvel item
                    </button>
                    <button
                      onClick={() => toggleExistingList(idx)}
                      className={`btn-glass text-sm ${
                        showExistingList[idx]
                          ? 'bg-blue-100 dark:bg-blue-500/20 text-blue-700 dark:text-blue-300'
                          : ''
                      }`}
                    >
                      <Search size={14} /> Voir les items existants
                    </button>
                  </div>

                  {/* Existing items list */}
                  {showExistingList[idx] && (
                    <div className="mt-3 p-3 bg-slate-50 dark:bg-slate-800/50 rounded-xl max-h-48 overflow-y-auto">
                      <div className="text-xs font-mono text-slate-500 mb-2">Items dans la base :</div>
                      {existingItems.slice(0, 15).map(ei => (
                        <button
                          key={ei.id_item}
                          onClick={() => handleDecision(idx, 'accept', ei.id_item)}
                          className={`w-full text-left px-3 py-2 rounded-lg text-sm mb-1 transition-colors ${
                            decisions[idx]?.targetItemId === ei.id_item
                              ? 'bg-emerald-100 dark:bg-emerald-500/20 text-emerald-700'
                              : 'hover:bg-slate-100 dark:hover:bg-slate-700/50 text-slate-600 dark:text-slate-300'
                          }`}
                        >
                          {ei.libelle_canonique}
                          {ei.usage_count > 0 && (
                            <span className="text-xs text-slate-400 ml-2">({ei.usage_count} utilisations)</span>
                          )}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* No Match */}
      {noMatch.length > 0 && (
        <div className="glass-card">
          <h3 className="font-display font-bold text-pink-600 mb-3 flex items-center gap-2">
            <ShieldCheck size={18} />
            Nouveaux items à créer ({noMatch.length})
          </h3>
          <div className="space-y-2">
            {noMatch.map((item, idx) => (
              <div key={idx} className="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-300">
                <span className="w-2 h-2 rounded-full bg-pink-400" />
                {item.description}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Save Section */}
      <div className="glass-card flex flex-col sm:flex-row justify-between items-center gap-4">
        <label className="flex items-center gap-2 text-sm cursor-pointer">
          <input
            type="checkbox"
            checked={forceOverwrite}
            onChange={(e) => onForceOverwriteChange(e.target.checked)}
            className="rounded border-slate-300"
          />
          Écraser si existante
        </label>
        <button onClick={onSave} className="btn-primary">
          <Save size={18} />
          Enregistrer dans la base
        </button>
      </div>
    </div>
  );
}