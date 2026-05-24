// components/SemanticValidation.jsx
import { useState, useMemo, useEffect } from 'react';
import { 
    CheckCircle, AlertTriangle, Search, 
    Save, ChevronLeft, Brain, Sparkles, Plus, ChevronDown,
    Columns
} from 'lucide-react';

export default function SemanticValidation({ 
  items = [], 
  existingItems = [],
  columns = [],
  existingColumns = [],
  concessionId,
  onSave, 
  onBack, 
  forceOverwrite, 
  onForceOverwriteChange,
  initialTab = 'columns'
}) {
  
  // ---- État onglets ----
  const [activeTab, setActiveTab] = useState(initialTab);
  
  // ---- États items ----
  const [visibleCountItems, setVisibleCountItems] = useState(5);
  const [itemDecisions, setItemDecisions] = useState({});
  const [showItemList, setShowItemList] = useState({});
  const [searchTerms, setSearchTerms] = useState({});
  
  // ---- États colonnes ----
  const [visibleCountColumns, setVisibleCountColumns] = useState(5);
  const [columnDecisions, setColumnDecisions] = useState({});
  const [showColumnList, setShowColumnList] = useState({});
  const [columnSearchTerms, setColumnSearchTerms] = useState({});

  // ==================== LOGIQUE ITEMS ====================
  
  const sortedItems = useMemo(() => {
    if (!items || items.length === 0) return [];
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

  const defaultItemDecisions = useMemo(() => {
    if (!items || items.length === 0) return {};
    const decisionsMap = {};
    sortedItems.forEach((item) => {
      const originalIdx = items.findIndex(i => i.description === item.description);
      const score = item.semantic?.confiance || item.semantic?.suggested_item?.confiance || 0;
      const suggestedId = item.semantic?.suggested_item?.item_id || item.semantic?.item_id;
      const autoMatch = item.semantic?.auto_match === true;
      const textType = item.semantic?.text_type;
      
      // Ne jamais skip automatiquement - sauf si c'est vraiment du bruit
      if (textType === 'noise' && item.description.length < 5) {
        decisionsMap[originalIdx] = { decision: 'skip', targetItemId: null };
      } else if (autoMatch || (score >= 0.85 && suggestedId)) {
        decisionsMap[originalIdx] = { decision: 'link', targetItemId: suggestedId, preselected: true };
      } else if (score >= 0.70 && suggestedId) {
        decisionsMap[originalIdx] = { decision: 'link', targetItemId: suggestedId, preselected: false };
      } else {
        decisionsMap[originalIdx] = { decision: 'new', targetItemId: null };
      }
    });
    return decisionsMap;
  }, [sortedItems, items]);

  useEffect(() => {
    setItemDecisions(defaultItemDecisions);
  }, [defaultItemDecisions]);

  const handleItemDecision = (originalIdx, decision, targetItemId = null) => {
    setItemDecisions(prev => ({
      ...prev,
      [originalIdx]: { decision, targetItemId, preselected: false }
    }));
  };

  const toggleItemList = (idx) => {
    setShowItemList(prev => ({ ...prev, [idx]: !prev[idx] }));
  };

  // ==================== LOGIQUE COLONNES ====================
  
  const sortedColumns = useMemo(() => {
    if (!columns || columns.length === 0) return [];
    return [...columns].sort((a, b) => {
      const scoreA = a.confiance || 0;
      const scoreB = b.confiance || 0;
      return scoreB - scoreA;
    });
  }, [columns]);

  const defaultColumnDecisions = useMemo(() => {
    if (!columns || columns.length === 0) return {};
    const decisionsMap = {};
    sortedColumns.forEach((col, idx) => {
      const originalIdx = columns.findIndex(c => c.original === col.original);
      if (col.suggested) {
        decisionsMap[originalIdx] = { decision: 'link', targetColumnId: col.suggested.id_colonne, preselected: true };
      } else {
        decisionsMap[originalIdx] = { decision: 'new', targetColumnId: null, preselected: false };
      }
    });
    return decisionsMap;
  }, [sortedColumns, columns]);

  useEffect(() => {
    setColumnDecisions(defaultColumnDecisions);
  }, [defaultColumnDecisions]);

  const handleColumnDecision = (originalIdx, decision, targetColumnId = null) => {
    setColumnDecisions(prev => ({
      ...prev,
      [originalIdx]: { decision, targetColumnId, preselected: false }
    }));
  };

  const toggleColumnList = (idx) => {
    setShowColumnList(prev => ({ ...prev, [idx]: !prev[idx] }));
  };

  // ==================== UTILITAIRES ====================
  
  const getScoreInfo = (item) => {
    const score = item.semantic?.confiance || item.semantic?.suggested_item?.confiance || 0;
    const autoMatch = item.semantic?.auto_match === true;
    const textType = item.semantic?.text_type;
    
    if (textType === 'noise' && item.description?.length < 5) {
      return { label: 'Ignoré', color: 'text-slate-400 bg-slate-50', icon: <AlertTriangle size={14} className="text-slate-400" />, pct: 0 };
    }
    
    if (autoMatch || score >= 0.95) {
      return { label: 'Très bonne', color: 'text-emerald-500 bg-emerald-50', icon: <CheckCircle size={14} className="text-emerald-500" />, pct: Math.round(score * 100) };
    }
    if (score >= 0.80) {
      return { label: 'Bonne', color: 'text-blue-500 bg-blue-50', icon: <CheckCircle size={14} className="text-blue-500" />, pct: Math.round(score * 100) };
    }
    if (score >= 0.70) {
      return { label: 'Moyenne', color: 'text-amber-500 bg-amber-50', icon: <AlertTriangle size={14} className="text-amber-500" />, pct: Math.round(score * 100) };
    }
    if (score > 0) {
      return { label: 'Faible', color: 'text-red-500 bg-red-50', icon: <AlertTriangle size={14} className="text-red-500" />, pct: Math.round(score * 100) };
    }
    return { label: 'À vérifier', color: 'text-slate-500 bg-slate-50', icon: <AlertTriangle size={14} className="text-slate-500" />, pct: 0 };
  };

  const getColumnScoreInfo = (col) => {
    const score = col.confiance || 0;
    if (score >= 0.95) {
      return { label: 'Très bonne', color: 'text-emerald-500 bg-emerald-50', icon: <CheckCircle size={14} className="text-emerald-500" />, pct: Math.round(score * 100) };
    }
    if (score >= 0.80) {
      return { label: 'Bonne', color: 'text-blue-500 bg-blue-50', icon: <CheckCircle size={14} className="text-blue-500" />, pct: Math.round(score * 100) };
    }
    if (score >= 0.70) {
      return { label: 'Moyenne', color: 'text-amber-500 bg-amber-50', icon: <AlertTriangle size={14} className="text-amber-500" />, pct: Math.round(score * 100) };
    }
    if (score > 0) {
      return { label: 'Faible', color: 'text-red-500 bg-red-50', icon: <AlertTriangle size={14} className="text-red-500" />, pct: Math.round(score * 100) };
    }
    return { label: 'À vérifier', color: 'text-slate-500 bg-slate-50', icon: <AlertTriangle size={14} className="text-slate-500" />, pct: 0 };
  };

// components/SemanticValidation.jsx - Modifier la fonction getFilteredItems

  const getFilteredItems = (idx) => {
    const search = (searchTerms[idx] || '').toLowerCase();
    const allItems = existingItems || [];
    
    // 🔥 CORRECTION : Si pas de recherche, afficher TOUS les items (pas de limite)
    if (!search) {
      return allItems;
    }
    
    return allItems.filter(ei => 
      (ei.libelle_canonique || '').toLowerCase().includes(search)
    );
  };

  // De même pour les colonnes
  const getFilteredColumns = (idx) => {
    const search = (columnSearchTerms[idx] || '').toLowerCase();
    const allColumns = existingColumns || [];
    
    // 🔥 CORRECTION : Si pas de recherche, afficher TOUTES les colonnes
    if (!search) {
      return allColumns;
    }
    
    return allColumns.filter(col => 
      (col.libelle_canonique || '').toLowerCase().includes(search)
    );
  };

  // Statistiques
  const itemLinkedCount = Object.values(itemDecisions).filter(d => d?.decision === 'link').length;
  const itemNewCount = Object.values(itemDecisions).filter(d => d?.decision === 'new').length;
  const itemSkippedCount = Object.values(itemDecisions).filter(d => d?.decision === 'skip').length;

  const columnLinkedCount = Object.values(columnDecisions).filter(d => d?.decision === 'link').length;
  const columnNewCount = Object.values(columnDecisions).filter(d => d?.decision === 'new').length;
  const columnSkippedCount = Object.values(columnDecisions).filter(d => d?.decision === 'skip').length;

  const visibleItems = sortedItems.slice(0, visibleCountItems);
  const hasMoreItems = sortedItems.length > visibleCountItems;
  
  const visibleColumns = sortedColumns.slice(0, visibleCountColumns);
  const hasMoreColumns = sortedColumns.length > visibleCountColumns;

  const primaryColor = '#06b6d4';
  const primaryLight = 'rgba(6, 182, 212, 0.1)';

  const showTabs = columns.length > 0 && items.length > 0;

  // Si rien à valider
  if (items.length === 0 && columns.length === 0) {
    return (
      <div className="max-w-4xl mx-auto space-y-6 animate-fade-in">
        <div className="glass-card text-center py-12">
          <Brain size={48} className="mx-auto text-slate-400 mb-4" />
          <h3 className="font-display text-xl font-bold text-slate-800">Aucune validation nécessaire</h3>
          <p className="text-slate-500 mt-2">Tous les éléments ont été automatiquement associés.</p>
          <button onClick={onBack} className="btn-primary mt-6">Retour</button>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6 animate-fade-in">
      {/* En-tête */}
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
            {columns.length > 0 && `${columns.length} colonne(s)`}
            {columns.length > 0 && items.length > 0 && ' · '}
            {items.length > 0 && `${items.length} item(s)`} — Vérifiez et confirmez chaque association
          </p>
        </div>
        <button onClick={onBack} className="btn-glass">
          <ChevronLeft size={16} /> Retour
        </button>
      </div>

      {/* Onglets */}
      {showTabs && (
        <div className="flex gap-2 border-b border-slate-200 dark:border-slate-700">
          <button
            onClick={() => setActiveTab('columns')}
            className={`flex items-center gap-2 px-4 py-2 text-sm font-medium transition-all ${
              activeTab === 'columns' 
                ? 'border-b-2 border-cyan-500 text-cyan-600' 
                : 'text-slate-500 hover:text-slate-700'
            }`}
          >
            <Columns size={14} />
            Colonnes
            <span className="ml-1 text-xs px-1.5 py-0.5 rounded-full bg-slate-100">
              {columns.length}
            </span>
          </button>
          <button
            onClick={() => setActiveTab('items')}
            className={`flex items-center gap-2 px-4 py-2 text-sm font-medium transition-all ${
              activeTab === 'items' 
                ? 'border-b-2 border-cyan-500 text-cyan-600' 
                : 'text-slate-500 hover:text-slate-700'
            }`}
          >
            <CheckCircle size={14} />
            Items
            <span className="ml-1 text-xs px-1.5 py-0.5 rounded-full bg-slate-100">
              {items.length}
            </span>
          </button>
        </div>
      )}

      {/* ==================== SECTION COLONNES ==================== */}
      {(activeTab === 'columns' || !showTabs) && columns.length > 0 && (
        <>
          {/* Statistiques colonnes */}
          <div className="grid grid-cols-3 gap-3">
            <div className="glass-card text-center py-4 border-l-4" style={{ borderLeftColor: primaryColor }}>
              <div className="text-2xl font-bold" style={{ color: primaryColor }}>{columnLinkedCount}</div>
              <div className="text-xs text-slate-500">Associées</div>
            </div>
            <div className="glass-card text-center py-4 border-l-4 border-blue-400">
              <div className="text-2xl font-bold text-blue-600">{columnNewCount}</div>
              <div className="text-xs text-slate-500">Nouvelles</div>
            </div>
            <div className="glass-card text-center py-4 border-l-4 border-slate-400">
              <div className="text-2xl font-bold text-slate-600">{columnSkippedCount}</div>
              <div className="text-xs text-slate-500">Ignorées</div>
            </div>
          </div>

          {/* Liste des colonnes */}
          <div className="space-y-3">
            {visibleColumns.map((col, displayIdx) => {
              const originalIdx = columns.findIndex(c => c.original === col.original);
              const decision = columnDecisions[originalIdx] || { decision: 'new', targetColumnId: null };
              const scoreInfo = getColumnScoreInfo(col);
              const isSkipped = decision.decision === 'skip';
              const isPreselected = decision.preselected && decision.decision === 'link';
              const suggestedLibelle = col.suggested?.libelle_canonique || '';

              return (
                <div key={`col-${displayIdx}`} className={`glass-card ${isSkipped ? 'opacity-50' : ''}`}>
                  <div className="flex items-start gap-4">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-2 flex-wrap">
                        <span className="font-semibold text-slate-800 dark:text-white truncate">
                          {col.original}
                        </span>
                        <span className="text-xs text-slate-400 bg-slate-100 px-2 py-0.5 rounded-full">
                          {col.section}
                        </span>
                        
                        {!isSkipped && (
                          <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-mono ${scoreInfo.color}`}>
                            {scoreInfo.icon}
                            {scoreInfo.label} ({scoreInfo.pct}%)
                          </span>
                        )}
                        
                        {isSkipped && (
                          <span className="px-2 py-0.5 rounded-full text-xs bg-slate-100 dark:bg-slate-800 text-slate-500">
                            Ignorée
                          </span>
                        )}

                        {isPreselected && (
                          <span className="px-2 py-0.5 rounded-full text-xs" style={{ backgroundColor: primaryLight, color: primaryColor }}>
                            <Sparkles size={12} className="inline mr-1" />
                            Pré-sélectionné
                          </span>
                        )}
                      </div>

                      {/* Suggestion IA - pour colonnes */}
                      {!isSkipped && suggestedLibelle && (
                        <div className="text-sm text-slate-500 dark:text-slate-400 mb-3">
                          Suggestion IA : 
                          <span className="font-medium ml-1" style={{ color: primaryColor }}>
                            {suggestedLibelle}
                          </span>
                        </div>
                      )}
                      
                      {/* Message si aucune correspondance */}
                      {!isSkipped && !suggestedLibelle && (
                        <div className="text-sm text-amber-600 mb-3 flex items-center gap-1">
                          <AlertTriangle size={14} />
                          Aucune correspondance trouvée
                        </div>
                      )}

                      {/* Boutons d'action */}
                      {!isSkipped && (
                        <div className="flex gap-2 flex-wrap">
                          <button
                            onClick={() => handleColumnDecision(originalIdx, 'link', col.suggested?.id_colonne || null)}
                            className={`btn-glass text-sm ${
                              decision.decision === 'link'
                                ? 'bg-emerald-100 dark:bg-emerald-500/20 text-emerald-700 dark:text-emerald-300 border-emerald-300'
                                : ''
                            }`}
                          >
                            <CheckCircle size={14} /> Associer
                          </button>
                          <button
                            onClick={() => handleColumnDecision(originalIdx, 'new')}
                            className={`btn-glass text-sm ${
                              decision.decision === 'new'
                                ? 'bg-blue-100 dark:bg-blue-500/20 text-blue-700 dark:text-blue-300 border-blue-300'
                                : ''
                            }`}
                          >
                            <Plus size={14} /> Nouvelle colonne
                          </button>
                          <button
                            onClick={() => toggleColumnList(originalIdx)}
                            className={`btn-glass text-sm ${
                              showColumnList[originalIdx]
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

                  {/* Liste des colonnes existantes */}
                  {showColumnList[originalIdx] && (
                    <div className="mt-3 pt-3 border-t border-slate-200 dark:border-slate-700">
                      <input
                        type="text"
                        placeholder="Rechercher une colonne..."
                        value={columnSearchTerms[originalIdx] || ''}
                        onChange={(e) => setColumnSearchTerms(prev => ({ ...prev, [originalIdx]: e.target.value }))}
                        className="input-glass mb-2 text-sm"
                      />
                      <div className="max-h-48 overflow-y-auto space-y-1">
                        {getFilteredColumns(originalIdx).length === 0 ? (
                          <div className="text-xs text-slate-400 text-center py-4">Aucune colonne trouvée</div>
                        ) : (
                          getFilteredColumns(originalIdx).map(colExistante => (
                            <button
                              key={colExistante.id_colonne}
                              onClick={() => {
                                handleColumnDecision(originalIdx, 'link', colExistante.id_colonne);
                                toggleColumnList(originalIdx);
                              }}
                              className={`w-full text-left px-3 py-2 rounded-lg text-sm transition-colors ${
                                decision.decision === 'link' && decision.targetColumnId === colExistante.id_colonne
                                  ? 'bg-emerald-100 dark:bg-emerald-500/20 text-emerald-700'
                                  : 'hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-600 dark:text-slate-300'
                              }`}
                            >
                              <div className="flex justify-between items-center">
                                <span>{colExistante.libelle_canonique}</span>
                                <span className="text-xs text-slate-400">
                                  {colExistante.usage_count > 0 ? `${colExistante.usage_count} util.` : ''}
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

          {/* Bouton "Voir plus" pour colonnes */}
          {hasMoreColumns && (
            <div className="flex justify-center">
              <button
                onClick={() => setVisibleCountColumns(prev => prev + 5)}
                className="btn-glass text-sm flex items-center gap-2"
              >
                <ChevronDown size={16} />
                Voir plus ({sortedColumns.length - visibleCountColumns} restants)
              </button>
            </div>
          )}
        </>
      )}

      {/* ==================== SECTION ITEMS (MÊME INTERFACE QUE COLONNES) ==================== */}
      {(activeTab === 'items' || !showTabs) && items.length > 0 && (
        <>
          {/* Statistiques items */}
          <div className="grid grid-cols-3 gap-3">
            <div className="glass-card text-center py-4 border-l-4" style={{ borderLeftColor: primaryColor }}>
              <div className="text-2xl font-bold" style={{ color: primaryColor }}>{itemLinkedCount}</div>
              <div className="text-xs text-slate-500">Associés</div>
            </div>
            <div className="glass-card text-center py-4 border-l-4 border-blue-400">
              <div className="text-2xl font-bold text-blue-600">{itemNewCount}</div>
              <div className="text-xs text-slate-500">Nouveaux</div>
            </div>
            <div className="glass-card text-center py-4 border-l-4 border-slate-400">
              <div className="text-2xl font-bold text-slate-600">{itemSkippedCount}</div>
              <div className="text-xs text-slate-500">Ignorés</div>
            </div>
          </div>

          {/* Liste des items */}
          <div className="space-y-3">
            {visibleItems.map((item, displayIdx) => {
              const originalIdx = items.findIndex(i => i.description === item.description);
              const decision = itemDecisions[originalIdx] || { decision: 'new', targetItemId: null };
              const scoreInfo = getScoreInfo(item);
              const isSkipped = decision.decision === 'skip';
              const isPreselected = decision.preselected && decision.decision === 'link';
              
              // Récupérer la suggestion IA correctement
              const suggestedLibelle = item.semantic?.suggested_item?.libelle || 
                                       item.semantic?.libelle || 
                                       item.semantic?.suggested_item?.libelle_canonique || 
                                       '';
              
              // Récupérer l'item matché pour affichage (si nécessaire)
              const matchedItem = existingItems.find(ei => ei.id_item === decision.targetItemId);

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

                      {/* Suggestion IA - comme pour les colonnes (pas de "Matché avec") */}
                      {!isSkipped && suggestedLibelle && (
                        <div className="text-sm text-slate-500 dark:text-slate-400 mb-3">
                          Suggestion IA : 
                          <span className="font-medium ml-1" style={{ color: primaryColor }}>
                            {suggestedLibelle}
                          </span>
                        </div>
                      )}
                      
                      {/* Message si aucune correspondance */}
                      {!isSkipped && !suggestedLibelle && scoreInfo.pct === 0 && (
                        <div className="text-sm text-amber-600 mb-3 flex items-center gap-1">
                          <AlertTriangle size={14} />
                          Aucune correspondance trouvée
                        </div>
                      )}

                      {!isSkipped && item.semantic?.message && !suggestedLibelle && (
                        <div className="text-xs text-slate-400 mb-3">{item.semantic.message}</div>
                      )}

                      {/* Boutons d'action */}
                      {!isSkipped && (
                        <div className="flex gap-2 flex-wrap">
                          <button
                            onClick={() => handleItemDecision(originalIdx, 'link', decision.targetItemId)}
                            className={`btn-glass text-sm ${
                              decision.decision === 'link'
                                ? 'bg-emerald-100 dark:bg-emerald-500/20 text-emerald-700 dark:text-emerald-300 border-emerald-300'
                                : ''
                            }`}
                          >
                            <CheckCircle size={14} /> Associer
                          </button>
                          <button
                            onClick={() => handleItemDecision(originalIdx, 'new')}
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
                                handleItemDecision(originalIdx, 'link', ei.id_item);
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

          {/* Bouton "Voir plus" pour items */}
          {hasMoreItems && (
            <div className="flex justify-center">
              <button
                onClick={() => setVisibleCountItems(prev => prev + 5)}
                className="btn-glass text-sm flex items-center gap-2"
              >
                <ChevronDown size={16} />
                Voir plus ({sortedItems.length - visibleCountItems} restants)
              </button>
            </div>
          )}
        </>
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
        <button onClick={() => onSave({ items: itemDecisions, columns: columnDecisions })} className="btn-primary" style={{ backgroundColor: primaryColor }}>
          <Save size={18} />
          Enregistrer avec mes choix
        </button>
      </div>
    </div>
  );
}