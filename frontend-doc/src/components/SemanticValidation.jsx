import { useState, useMemo } from 'react';
import { 
    CheckCircle, AlertTriangle, Search, 
    Save, ChevronLeft, Brain, Sparkles, Plus, ChevronDown
} from 'lucide-react';

export default function SemanticValidation({ 
  items, existingItems, 
  onSave, onBack, forceOverwrite, onForceOverwriteChange 
}) {
  
  const [visibleCount, setVisibleCount] = useState(5);
  const [decisions, setDecisions] = useState({});
  const [showItemList, setShowItemList] = useState({});
  const [searchTerms, setSearchTerms] = useState({});

  const sortedItems = useMemo(() => {
    return [...items].sort((a, b) => {
      const getPriority = (item) => {
        const score = item.semantic?.confiance || item.semantic?.suggested_item?.confiance || 0;
        const autoMatch = item.semantic?.auto_match === true;
        const textType = item.semantic?.text_type;
        
        if (score === 0 || textType === 'skip' || textType === 'noise' || textType === 'doc_ref') {
          return 0;
        }
        if (score >= 0.70 && score < 0.95 && !autoMatch) {
          return 1;
        }
        if (score >= 0.95 || autoMatch) {
          return 2;
        }
        return 3;
      };
      
      const priorityA = getPriority(a);
      const priorityB = getPriority(b);
      
      if (priorityA !== priorityB) return priorityA - priorityB;
      
      const scoreA = a.semantic?.confiance || a.semantic?.suggested_item?.confiance || 0;
      const scoreB = b.semantic?.confiance || b.semantic?.suggested_item?.confiance || 0;
      return scoreB - scoreA;
    });
  }, [items]);

  const defaultDecisions = useMemo(() => {
    const decisionsMap = {};
    sortedItems.forEach((item) => {
      const originalIdx = items.findIndex(i => i.description === item.description);
      const score = item.semantic?.confiance || item.semantic?.suggested_item?.confiance || 0;
      const suggestedId = item.semantic?.suggested_item?.item_id || item.semantic?.item_id;
      const autoMatch = item.semantic?.auto_match === true;
      
      if (item.semantic?.action === 'skip' || item.semantic?.text_type === 'noise' || item.semantic?.text_type === 'doc_ref') {
        decisionsMap[originalIdx] = { decision: 'skip', targetItemId: null };
      } else if (autoMatch || (score >= 0.95 && suggestedId)) {
        decisionsMap[originalIdx] = { decision: 'link', targetItemId: suggestedId, preselected: true };
      } else if (score >= 0.70 && suggestedId) {
        decisionsMap[originalIdx] = { decision: 'link', targetItemId: suggestedId, preselected: false };
      } else {
        decisionsMap[originalIdx] = { decision: 'new', targetItemId: null };
      }
    });
    return decisionsMap;
  }, [sortedItems, items]);

  useState(() => {
    setDecisions(defaultDecisions);
  }, [defaultDecisions]);

  const handleDecision = (originalIdx, decision, targetItemId = null) => {
    setDecisions(prev => ({
      ...prev,
      [originalIdx]: { decision, targetItemId, preselected: false }
    }));
  };

  const toggleItemList = (idx) => {
    setShowItemList(prev => ({ ...prev, [idx]: !prev[idx] }));
  };

  const getScoreInfo = (item) => {
    const score = item.semantic?.confiance || item.semantic?.suggested_item?.confiance || 0;
    const autoMatch = item.semantic?.auto_match === true;
    const textType = item.semantic?.text_type;
    
    if (textType === 'skip' || textType === 'noise' || textType === 'doc_ref') {
      return { label: 'Ignoré', color: 'text-slate-400 bg-slate-50 dark:bg-slate-800', icon: <AlertTriangle size={14} className="text-slate-400" />, pct: 0, priority: 0 };
    }
    
    if (autoMatch || score >= 0.95) {
      return { label: 'Forte', color: 'text-emerald-500 bg-emerald-50 dark:bg-emerald-500/10', icon: <CheckCircle size={14} className="text-emerald-500" />, pct: Math.round(score * 100), priority: 2 };
    }
    if (score >= 0.70) {
      return { label: 'Moyenne', color: 'text-amber-500 bg-amber-50 dark:bg-amber-500/10', icon: <AlertTriangle size={14} className="text-amber-500" />, pct: Math.round(score * 100), priority: 1 };
    }
    return { label: 'Faible', color: 'text-red-500 bg-red-50 dark:bg-red-500/10', icon: <AlertTriangle size={14} className="text-red-500" />, pct: Math.round(score * 100), priority: 0 };
  };

  const getFilteredItems = (idx) => {
    const search = (searchTerms[idx] || '').toLowerCase();
    const allItems = existingItems || [];
    if (!search) return allItems;
    return allItems.filter(ei => 
      (ei.libelle_canonique || '').toLowerCase().includes(search)
    );
  };

  const linkedCount = Object.values(decisions).filter(d => d.decision === 'link').length;
  const newCount = Object.values(decisions).filter(d => d.decision === 'new').length;
  const skippedCount = Object.values(decisions).filter(d => d.decision === 'skip').length;

  const visibleItems = sortedItems.slice(0, visibleCount);
  const hasMore = sortedItems.length > visibleCount;

  // Couleur principale de l'interface
  const primaryColor = '#06b6d4';
  const primaryLight = 'rgba(6, 182, 212, 0.1)';

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2 text-xs font-mono uppercase tracking-wider mb-1" style={{ color: primaryColor }}>
            <Brain size={14} />
            Validation semantique
          </div>
          <h2 className="font-display text-2xl font-extrabold text-slate-800 dark:text-white">
            Verifier chaque <span style={{ color: primaryColor }}>correspondance</span>
          </h2>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
            {items.length} items extraits — Verifiez et confirmez chaque association
          </p>
        </div>
        <button onClick={onBack} className="btn-glass">
          <ChevronLeft size={16} /> Retour
        </button>
      </div>

      {/* Statistiques */}
      <div className="grid grid-cols-3 gap-3">
        <div className="glass-card text-center py-4 border-l-4" style={{ borderLeftColor: primaryColor }}>
          <div className="text-2xl font-bold" style={{ color: primaryColor }}>{linkedCount}</div>
          <div className="text-xs text-slate-500">Associes</div>
        </div>
        <div className="glass-card text-center py-4 border-l-4 border-blue-400">
          <div className="text-2xl font-bold text-blue-600">{newCount}</div>
          <div className="text-xs text-slate-500">Nouveaux</div>
        </div>
        <div className="glass-card text-center py-4 border-l-4 border-slate-400">
          <div className="text-2xl font-bold text-slate-600">{skippedCount}</div>
          <div className="text-xs text-slate-500">Ignorés</div>
        </div>
      </div>

      {/* Liste des items triés */}
      <div className="space-y-3">
        {visibleItems.map((item, displayIdx) => {
          const originalIdx = items.findIndex(i => i.description === item.description);
          const decision = decisions[originalIdx] || { decision: 'new', targetItemId: null };
          const scoreInfo = getScoreInfo(item);
          const isSkipped = decision.decision === 'skip';
          const isPreselected = decision.preselected && decision.decision === 'link';
          const suggestedLibelle = item.semantic?.suggested_item?.libelle || '';

          return (
            <div key={displayIdx} className={`glass-card ${isSkipped ? 'opacity-50' : ''}`}>
              <div className="flex items-start gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-2 flex-wrap">
                    <span className="font-semibold text-slate-800 dark:text-white truncate">
                      {item.description}
                    </span>
                    
                    {!isSkipped && (
                      <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-mono ${scoreInfo.color}`}>
                        {scoreInfo.icon}
                        {scoreInfo.label} ({scoreInfo.pct}%)
                      </span>
                    )}
                    
                    {isSkipped && (
                      <span className="px-2 py-0.5 rounded-full text-xs bg-slate-100 dark:bg-slate-800 text-slate-500">
                        Ignoré
                      </span>
                    )}

                    {isPreselected && (
                      <span className="px-2 py-0.5 rounded-full text-xs" style={{ backgroundColor: primaryLight, color: primaryColor }}>
                        <Sparkles size={12} className="inline mr-1" />
                        Pré-sélectionné
                      </span>
                    )}
                  </div>

                  {/* Suggestion IA */}
                  {!isSkipped && suggestedLibelle && (
                    <div className="text-sm text-slate-500 dark:text-slate-400 mb-3">
                      Suggestion IA : 
                      <span className="font-medium ml-1" style={{ color: primaryColor }}>
                        {suggestedLibelle}
                      </span>
                    </div>
                  )}
                  
                  {/* Afficher l'item matché quand pré-sélectionné */}
                  {isPreselected && decision.targetItemId && (
                    <div className="text-sm text-slate-500 dark:text-slate-400 mb-3">
                      Matché avec : 
                      <span className="font-medium ml-1" style={{ color: primaryColor }}>
                        {existingItems.find(ei => ei.id_item === decision.targetItemId)?.libelle_canonique || 'Item inconnu'}
                      </span>
                    </div>
                  )}

                  {!isSkipped && item.semantic?.message && (
                    <div className="text-xs text-slate-400 mb-3">{item.semantic.message}</div>
                  )}

                  {/* Boutons d'action */}
                  {!isSkipped && (
                    <div className="flex gap-2 flex-wrap">
                      <button
                        onClick={() => handleDecision(originalIdx, 'link', decision.targetItemId)}
                        className={`btn-glass text-sm ${
                          decision.decision === 'link'
                            ? 'bg-emerald-100 dark:bg-emerald-500/20 text-emerald-700 dark:text-emerald-300 border-emerald-300'
                            : ''
                        }`}
                      >
                        <CheckCircle size={14} /> Associer
                      </button>
                      <button
                        onClick={() => handleDecision(originalIdx, 'new')}
                        className={`btn-glass text-sm ${
                          decision.decision === 'new'
                            ? 'bg-blue-100 dark:bg-blue-500/20 text-blue-700 dark:text-blue-300 border-blue-300'
                            : ''
                        }`}
                      >
                        <Plus size={14} /> Nouvel item
                      </button>
                      <button
                        onClick={() => toggleItemList(originalIdx)}
                        className={`btn-glass text-sm ${
                          showItemList[originalIdx]
                            ? 'bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-200'
                            : ''
                        }`}
                      >
                        <Search size={14} /> Parcourir la base
                      </button>
                    </div>
                  )}
                </div>
              </div>

              {/* Liste des items existants */}
              {showItemList[originalIdx] && (
                <div className="mt-3 pt-3 border-t border-slate-200 dark:border-slate-700">
                  <input
                    type="text"
                    placeholder="Rechercher un item..."
                    value={searchTerms[originalIdx] || ''}
                    onChange={(e) => setSearchTerms(prev => ({ ...prev, [originalIdx]: e.target.value }))}
                    className="input-glass mb-2 text-sm"
                  />
                  <div className="max-h-48 overflow-y-auto space-y-1">
                    {getFilteredItems(originalIdx).length === 0 ? (
                      <div className="text-xs text-slate-400 text-center py-4">Aucun item trouvé</div>
                    ) : (
                      getFilteredItems(originalIdx).map(ei => (
                        <button
                          key={ei.id_item}
                          onClick={() => {
                            handleDecision(originalIdx, 'link', ei.id_item);
                            toggleItemList(originalIdx);
                          }}
                          className={`w-full text-left px-3 py-2 rounded-lg text-sm transition-colors ${
                            decision.decision === 'link' && decision.targetItemId === ei.id_item
                              ? 'bg-emerald-100 dark:bg-emerald-500/20 text-emerald-700'
                              : 'hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-600 dark:text-slate-300'
                          }`}
                        >
                          <div className="flex justify-between items-center">
                            <span>{ei.libelle_canonique}</span>
                            <span className="text-xs text-slate-400">
                              {ei.statut === 'actif' ? '' : `(${ei.statut || 'actif'})`}
                              {ei.usage_count > 0 ? ` · ${ei.usage_count} util.` : ''}
                            </span>
                          </div>
                        </button>
                      ))
                    )}
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Bouton "Voir plus" */}
      {hasMore && (
        <div className="flex justify-center">
          <button
            onClick={() => setVisibleCount(prev => prev + 5)}
            className="btn-glass text-sm flex items-center gap-2"
          >
            <ChevronDown size={16} />
            Voir plus ({sortedItems.length - visibleCount} restants)
          </button>
        </div>
      )}

      {/* Boutons de validation finale */}
      <div className="glass-card flex flex-col sm:flex-row justify-between items-center gap-4 sticky bottom-4">
        <label className="flex items-center gap-2 text-sm cursor-pointer">
          <input
            type="checkbox"
            checked={forceOverwrite}
            onChange={(e) => onForceOverwriteChange(e.target.checked)}
            className="rounded border-slate-300"
          />
          Écraser si existante
        </label>
        <button onClick={() => onSave(decisions)} className="btn-primary" style={{ backgroundColor: primaryColor }}>
          <Save size={18} />
          Enregistrer avec mes choix
        </button>
      </div>
    </div>
  );
}