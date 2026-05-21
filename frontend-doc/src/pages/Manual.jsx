import { useState, useEffect } from 'react';
import { useApp } from '../context/AppContext';
import { apiCall } from '../api/api';
import { PenTool, Plus, Save, Building2, List, Trash2, Columns, X, Edit2, Check } from 'lucide-react';

const primaryColor = '#06b6d4';

export default function Manual() {
  const { showSpinner, hideSpinner, showToast, concessionsList, setConcessionsList } = useApp();
  const [selectedConcession, setSelectedConcession] = useState('');
  const [newConcessionName, setNewConcessionName] = useState('');
  const [meta, setMeta] = useState({ date: '', devise: 'EUR', numero: '' });
  const [forceOverwrite, setForceOverwrite] = useState(false);
  const [showItemsModal, setShowItemsModal] = useState(false);
  const [showColsModal, setShowColsModal] = useState(false);
  const [showAddColumnModal, setShowAddColumnModal] = useState(false);
  const [showEditColumnModal, setShowEditColumnModal] = useState(false);
  const [newColumnName, setNewColumnName] = useState('');
  const [editingColumnName, setEditingColumnName] = useState('');
  const [editingColumnOldName, setEditingColumnOldName] = useState('');
  const [availableItems, setAvailableItems] = useState([]);
  const [availableCols, setAvailableCols] = useState([]);
  const [selectedItems, setSelectedItems] = useState([]);
  const [formReady, setFormReady] = useState(false);
  
  const [tableColumns, setTableColumns] = useState(['Description']);
  const [tableRows, setTableRows] = useState([{ Description: '' }]);
  const [editingCell, setEditingCell] = useState(null);
  const [editingRowIndex, setEditingRowIndex] = useState(null);
  const [editingRowData, setEditingRowData] = useState({});

  useEffect(() => {
    apiCall('GET', '/concessions')
      .then(setConcessionsList)
      .catch(() => {});
  }, [setConcessionsList]);

  const resetForm = () => {
    setFormReady(false);
    setSelectedItems([]);
    setTableColumns(['Description']);
    setTableRows([{ Description: '' }]);
    setMeta({ date: '', devise: 'EUR', numero: '' });
    setAvailableItems([]);
    setAvailableCols([]);
    setShowItemsModal(false);
    setShowColsModal(false);
    setShowAddColumnModal(false);
    setShowEditColumnModal(false);
    setNewColumnName('');
    setEditingCell(null);
    setEditingRowIndex(null);
    setEditingRowData({});
  };

  const selectConcession = async (id) => {
    resetForm();
    setSelectedConcession(id);
    
    if (!id) return;

    showSpinner();
    try {
      const items = await apiCall('GET', '/items', null, { id_concession: id });
      const itemLabels = items.map(it => it.libelle_canonique).filter(Boolean);
      setAvailableItems(itemLabels);
      
      const colonnes = await apiCall('GET', '/colonnes', null, { id_concession: id });
      const colLabels = colonnes.map(c => c.libelle_canonique);
      setAvailableCols(colLabels);
      
      if (itemLabels.length === 0 && colLabels.length === 0) {
        setFormReady(true);
        setTableColumns(['Description']);
        setTableRows([{ Description: '' }]);
        showToast('Aucun item ni colonne existant. Vous pouvez ajouter des lignes et colonnes manuellement.', 'info');
      } else if (itemLabels.length > 0) {
        setShowItemsModal(true);
      } else {
        setShowColsModal(true);
      }
    } catch (error) {
      console.error('Erreur chargement:', error);
      setFormReady(true);
      setTableColumns(['Description']);
      setTableRows([{ Description: '' }]);
      showToast('Erreur lors du chargement, création d\'un tableau vide', 'warning');
    } finally {
      hideSpinner();
    }
  };

  const promptCols = async (descriptions) => {
    setSelectedItems(descriptions);
    setShowItemsModal(false);
    
    if (availableCols.length > 0) {
      const cols = availableCols.includes('Description') ? availableCols : ['Description', ...availableCols];
      finalizeTable(cols, descriptions);
    } else {
      setShowColsModal(true);
    }
  };

  const finalizeTable = (cols, descriptions) => {
    setShowColsModal(false);
    setFormReady(true);
    setTableColumns(cols);
    
    if (descriptions && descriptions.length > 0) {
      const rows = descriptions.map(d => {
        const row = { Description: d };
        cols.forEach(col => { if (col !== 'Description') row[col] = ''; });
        return row;
      });
      setTableRows(rows);
    } else {
      const emptyRow = { Description: '' };
      cols.forEach(col => { if (col !== 'Description') emptyRow[col] = ''; });
      setTableRows([emptyRow]);
    }
  };

  const handleCreateConcession = async () => {
    if (!newConcessionName.trim()) {
      showToast('Veuillez entrer un nom de concession', 'warning');
      return;
    }
    showSpinner();
    try {
      const newC = await apiCall('POST', '/concessions', { nom: newConcessionName.trim() });
      setConcessionsList(prev => [...prev, newC]);
      setNewConcessionName('');
      showToast('Concession créée', 'success');
      resetForm();
      setSelectedConcession(newC.id_concession);
      setFormReady(true);
      setTableColumns(['Description']);
      setTableRows([{ Description: '' }]);
    } catch (error) {
      console.error('Erreur création concession:', error);
      showToast('Erreur création concession', 'danger');
    } finally {
      hideSpinner();
    }
  };

  // ==================== GESTION DES CELLULES ====================
  const handleCellEdit = (rowIdx, col, value) => {
    setTableRows(prev => prev.map((row, i) =>
      i === rowIdx ? { ...row, [col]: value } : row
    ));
    setEditingCell(null);
  };

  const startCellEdit = (rowIdx, col) => {
    setEditingCell({ rowIdx, col });
  };

  // ==================== GESTION DES LIGNES ====================
  const handleAddRow = () => {
    const emptyRow = {};
    tableColumns.forEach(col => { emptyRow[col] = ''; });
    setTableRows(prev => [...prev, emptyRow]);
    showToast('Nouvelle ligne ajoutée', 'success');
  };

  const handleDeleteRow = (rowIdx) => {
    if (tableRows.length <= 1) {
      showToast('Il doit rester au moins une ligne', 'warning');
      return;
    }
    if (window.confirm(`Supprimer cette ligne ?`)) {
      setTableRows(prev => prev.filter((_, i) => i !== rowIdx));
      showToast('Ligne supprimée', 'success');
    }
  };

  const startEditRow = (rowIdx) => {
    setEditingRowIndex(rowIdx);
    setEditingRowData({ ...tableRows[rowIdx] });
  };

  const cancelEditRow = () => {
    setEditingRowIndex(null);
    setEditingRowData({});
  };

  const saveEditRow = (rowIdx) => {
    setTableRows(prev => prev.map((row, i) => 
      i === rowIdx ? { ...editingRowData } : row
    ));
    setEditingRowIndex(null);
    setEditingRowData({});
    showToast('Ligne modifiée', 'success');
  };

  const handleRowFieldChange = (col, value) => {
    setEditingRowData(prev => ({ ...prev, [col]: value }));
  };

  // ==================== GESTION DES COLONNES ====================
  const openAddColumnModal = () => {
    setNewColumnName('');
    setShowAddColumnModal(true);
  };

  const confirmAddColumn = () => {
    const name = newColumnName.trim();
    if (!name) {
      showToast('Veuillez entrer un nom de colonne', 'warning');
      return;
    }
    if (tableColumns.includes(name)) {
      showToast('Cette colonne existe déjà', 'warning');
      return;
    }
    setTableColumns(prev => [...prev, name]);
    setTableRows(prev => prev.map(row => ({ ...row, [name]: '' })));
    setShowAddColumnModal(false);
    setNewColumnName('');
    showToast(`Colonne "${name}" ajoutée`, 'success');
  };

  const openEditColumnModal = (colName) => {
    setEditingColumnOldName(colName);
    setEditingColumnName(colName);
    setShowEditColumnModal(true);
  };

  const confirmEditColumn = () => {
    const newName = editingColumnName.trim();
    if (!newName) {
      showToast('Veuillez entrer un nom de colonne', 'warning');
      return;
    }
    if (newName === editingColumnOldName) {
      setShowEditColumnModal(false);
      return;
    }
    if (tableColumns.includes(newName)) {
      showToast('Ce nom de colonne existe déjà', 'warning');
      return;
    }
    
    // Renommer la colonne dans toutes les lignes
    setTableColumns(prev => prev.map(col => col === editingColumnOldName ? newName : col));
    setTableRows(prev => prev.map(row => {
      const newRow = { ...row };
      if (newRow[editingColumnOldName] !== undefined) {
        newRow[newName] = newRow[editingColumnOldName];
        delete newRow[editingColumnOldName];
      }
      return newRow;
    }));
    
    setShowEditColumnModal(false);
    setEditingColumnName('');
    setEditingColumnOldName('');
    showToast(`Colonne renommée en "${newName}"`, 'success');
  };

  const handleDeleteColumn = (colName) => {
    if (colName === 'Description') {
      showToast('La colonne Description ne peut pas être supprimée', 'warning');
      return;
    }
    if (window.confirm(`Supprimer la colonne "${colName}" ? Cette action supprimera toutes les valeurs de cette colonne.`)) {
      setTableColumns(prev => prev.filter(col => col !== colName));
      setTableRows(prev => prev.map(row => {
        const newRow = { ...row };
        delete newRow[colName];
        return newRow;
      }));
      showToast(`Colonne "${colName}" supprimée`, 'success');
    }
  };

  // ==================== SAUVEGARDE ====================
  const getTableData = () => {
    const [descCol, ...valueCols] = tableColumns;
    return tableRows.map(row => {
      const valeurs = {};
      valueCols.forEach(col => {
        if (row[col] !== undefined && row[col] !== '') valeurs[col] = String(row[col]);
      });
      return { description: row[descCol] || '', valeurs };
    });
  };

  const saveFacture = async () => {
    if (!selectedConcession) {
      showToast('Sélectionnez une concession', 'warning');
      return;
    }
    
    const tableData = getTableData();
    if (!tableData.length || (tableData.length === 1 && !tableData[0].description && Object.keys(tableData[0].valeurs).length === 0)) {
      showToast('Ajoutez au moins un article', 'warning');
      return;
    }

    showSpinner();
    try {
      await apiCall('POST', '/facture', {
        facture: {
          fichier_source: 'saisie_manuelle',
          date_facture: meta.date || null,
          devise: meta.devise,
          id_concession: parseInt(selectedConcession),
          numero_facture: meta.numero || null,
          total_montant: 0,
        },
        items_data: tableData,
      }, { force: forceOverwrite });

      showToast('Facture enregistrée', 'success');
      resetForm();
      setSelectedConcession('');
    } catch (err) {
      console.error('Erreur enregistrement:', err);
      if (err?.response?.status === 409) {
        showToast('Facture existante. Cochez "Écraser si existe".', 'warning');
      } else {
        showToast('Erreur enregistrement', 'danger');
      }
    } finally {
      hideSpinner();
    }
  };

  return (
    <div className="max-w-7xl mx-auto space-y-6 animate-fade-in">
      <h1 className="font-display text-3xl font-extrabold text-slate-800 dark:text-white flex items-center gap-3">
        <PenTool style={{ color: primaryColor }} />
        Saisie manuelle
      </h1>

      {/* Step 1: Concession */}
      <div className="glass-card">
        <h3 className="font-display font-bold text-lg mb-4 flex items-center gap-2">
          <Building2 size={20} style={{ color: primaryColor }} />
          Concession
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 items-end">
          <select
            value={selectedConcession}
            onChange={(e) => selectConcession(e.target.value)}
            className="select-glass input-glass"
          >
            <option value="">-- Choisir --</option>
            {concessionsList.map(c => (
              <option key={c.id_concession} value={c.id_concession}>{c.nom}</option>
            ))}
          </select>
          <div className="flex gap-2">
            <input
              type="text"
              placeholder="Nouvelle concession"
              value={newConcessionName}
              onChange={(e) => setNewConcessionName(e.target.value)}
              className="input-glass flex-1"
              onKeyDown={(e) => e.key === 'Enter' && handleCreateConcession()}
            />
            <button onClick={handleCreateConcession} className="btn-primary">Créer</button>
          </div>
        </div>
      </div>

      {/* Step 2: Metadata */}
      {formReady && (
        <div className="glass-card animate-slide-up">
          <h3 className="font-display font-bold text-lg mb-4">Métadonnées</h3>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <input 
              type="date" 
              value={meta.date} 
              onChange={(e) => setMeta(p => ({ ...p, date: e.target.value }))} 
              className="input-glass" 
              placeholder="Date" 
            />
            <input 
              type="text" 
              value={meta.devise} 
              onChange={(e) => setMeta(p => ({ ...p, devise: e.target.value }))} 
              className="input-glass" 
              placeholder="Devise" 
            />
            <input 
              type="text" 
              value={meta.numero} 
              onChange={(e) => setMeta(p => ({ ...p, numero: e.target.value }))} 
              className="input-glass" 
              placeholder="Numéro" 
            />
          </div>
        </div>
      )}

      {/* Step 3: Articles Table */}
      {formReady && (
        <div className="glass-card animate-slide-up p-4">
          <div className="flex justify-between items-center mb-4">
            <h3 className="font-display font-bold text-lg text-slate-800 dark:text-white">Articles</h3>
            <div className="flex gap-2">
              <button onClick={() => {
                apiCall('GET', '/items', null, { id_concession: selectedConcession })
                  .then(items => {
                    const itemLabels = items.map(it => it.libelle_canonique).filter(Boolean);
                    setAvailableItems(itemLabels);
                    setShowItemsModal(true);
                  })
                  .catch(() => showToast('Erreur chargement items', 'danger'));
              }} className="btn-glass text-sm">
                <List size={16} /> Items existants
              </button>
              <button onClick={openAddColumnModal} className="btn-glass text-sm">
                <Columns size={16} /> Ajouter colonne
              </button>
              <button onClick={handleAddRow} className="btn-glass text-sm">
                <Plus size={16} /> Ajouter ligne
              </button>
            </div>
          </div>

          <div className="overflow-x-auto rounded-xl border border-slate-200/30 dark:border-slate-700/30">
            {tableRows.length === 0 ? (
              <p className="text-center text-slate-400 dark:text-slate-500 py-10 italic">
                Aucune donnée
              </p>
            ) : (
              <table className="w-full text-sm" style={{ minWidth: '100%' }}>
                <thead>
                  <tr className="bg-gradient-to-r from-blue-50/80 to-cyan-50/80 dark:from-blue-950/30 dark:to-cyan-950/20">
                    {tableColumns.map((col) => (
                      <th
                        key={col}
                        className="px-4 py-3 text-left font-mono text-xs uppercase tracking-wider whitespace-nowrap"
                        style={{ color: primaryColor }}
                      >
                        {col}
                        <div className="inline-flex ml-2 gap-1">
                          {col !== 'Description' && (
                            <>
                              <button
                                onClick={() => openEditColumnModal(col)}
                                className="text-slate-400 hover:text-blue-500 transition-colors"
                                title="Renommer la colonne"
                              >
                                <Edit2 size={12} />
                              </button>
                              <button
                                onClick={() => handleDeleteColumn(col)}
                                className="text-slate-400 hover:text-red-500 transition-colors"
                                title="Supprimer la colonne"
                              >
                                <Trash2 size={12} />
                              </button>
                            </>
                          )}
                        </div>
                      </th>
                    ))}
                    <th className="px-4 py-3 w-20 text-center">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-blue-100/50 dark:divide-slate-800/50">
                  {tableRows.map((row, rowIdx) => {
                    const isEditingRow = editingRowIndex === rowIdx;
                    
                    if (isEditingRow) {
                      return (
                        <tr key={rowIdx} className="bg-cyan-50/50 dark:bg-cyan-950/20">
                          {tableColumns.map((col) => (
                            <td key={col} className="px-4 py-2">
                              <input
                                type="text"
                                value={editingRowData[col] || ''}
                                onChange={(e) => handleRowFieldChange(col, e.target.value)}
                                className="w-full bg-transparent border-b border-cyan-400 focus:outline-none px-2 py-1"
                                autoFocus={col === tableColumns[0]}
                                placeholder={col}
                              />
                             </td>
                          ))}
                          <td className="px-2 py-2 text-center whitespace-nowrap">
                            <button
                              onClick={() => saveEditRow(rowIdx)}
                              className="p-1 text-green-500 hover:text-green-600 transition-colors mr-1"
                              title="Valider"
                            >
                              <Check size={16} />
                            </button>
                            <button
                              onClick={cancelEditRow}
                              className="p-1 text-red-500 hover:text-red-600 transition-colors"
                              title="Annuler"
                            >
                              <X size={16} />
                            </button>
                          </td>
                        </tr>
                      );
                    }
                    
                    return (
                      <tr
                        key={rowIdx}
                        className="hover:bg-blue-50/30 dark:hover:bg-slate-800/30 transition-colors"
                      >
                        {tableColumns.map((col, colIdx) => {
                          const isEditing = editingCell?.rowIdx === rowIdx && editingCell?.col === col;
                          const isFirst = colIdx === 0;
                          return (
                            <td
                              key={col}
                              className={`px-4 py-2 whitespace-nowrap cursor-pointer ${
                                isFirst
                                  ? 'font-medium text-slate-800 dark:text-slate-200'
                                  : 'font-mono text-right text-slate-600 dark:text-slate-400'
                              }`}
                              onDoubleClick={() => startCellEdit(rowIdx, col)}
                            >
                              {isEditing ? (
                                <input
                                  autoFocus
                                  className="w-full bg-transparent outline-none border-b border-cyan-400 dark:border-cyan-500 text-slate-800 dark:text-slate-100 text-sm px-2"
                                  defaultValue={row[col] || ''}
                                  onBlur={(e) => handleCellEdit(rowIdx, col, e.target.value)}
                                  onKeyDown={(e) => { 
                                    if (e.key === 'Enter') handleCellEdit(rowIdx, col, e.target.value);
                                    if (e.key === 'Escape') setEditingCell(null);
                                  }}
                                />
                              ) : (
                                <span className="truncate block max-w-[200px]" title={row[col]}>
                                  {row[col] || '—'}
                                </span>
                              )}
                             </td>
                          );
                        })}
                        <td className="px-2 py-2 text-center whitespace-nowrap">
                          <button
                            onClick={() => startEditRow(rowIdx)}
                            className="p-1 text-blue-500 hover:text-blue-600 transition-colors mr-1"
                            title="Modifier la ligne"
                          >
                            <Edit2 size={14} />
                          </button>
                          <button
                            onClick={() => handleDeleteRow(rowIdx)}
                            className="p-1 text-red-500 hover:text-red-600 transition-colors"
                            title="Supprimer la ligne"
                          >
                            <Trash2 size={14} />
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>

          <p className="text-right text-xs font-mono text-slate-400 dark:text-slate-500 mt-2">
            Double-cliquez sur une cellule pour l'éditer
          </p>

          <div className="flex items-center justify-between mt-6 pt-6 border-t border-slate-200/50 dark:border-slate-700/30">
            <label className="flex items-center gap-2 text-sm cursor-pointer text-slate-600 dark:text-slate-300">
              <input
                type="checkbox"
                checked={forceOverwrite}
                onChange={(e) => setForceOverwrite(e.target.checked)}
                className="rounded border-slate-300 dark:border-slate-600 accent-cyan-500"
              />
              Écraser si existe
            </label>
            <button onClick={saveFacture} className="btn-primary">
              <Save size={18} />
              Enregistrer la facture
            </button>
          </div>
        </div>
      )}

      {/* Modal Ajout Colonne */}
      {showAddColumnModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm" onClick={() => setShowAddColumnModal(false)}>
          <div className="glass-card w-96" onClick={e => e.stopPropagation()}>
            <div className="flex justify-between items-center mb-4">
              <h3 className="font-bold text-lg flex items-center gap-2">
                <Columns size={18} style={{ color: primaryColor }} />
                Ajouter une colonne
              </h3>
              <button onClick={() => setShowAddColumnModal(false)} className="p-1 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800">
                <X size={18} className="text-slate-500" />
              </button>
            </div>
            <input
              type="text"
              value={newColumnName}
              onChange={(e) => setNewColumnName(e.target.value)}
              placeholder="Nom de la colonne"
              className="input-glass w-full mb-4"
              autoFocus
              onKeyDown={(e) => { if (e.key === 'Enter') confirmAddColumn(); }}
            />
            <div className="flex gap-2">
              <button onClick={() => setShowAddColumnModal(false)} className="btn-glass flex-1">Annuler</button>
              <button onClick={confirmAddColumn} className="btn-primary flex-1">Ajouter</button>
            </div>
          </div>
        </div>
      )}

      {/* Modal Renommer Colonne */}
      {showEditColumnModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm" onClick={() => setShowEditColumnModal(false)}>
          <div className="glass-card w-96" onClick={e => e.stopPropagation()}>
            <div className="flex justify-between items-center mb-4">
              <h3 className="font-bold text-lg flex items-center gap-2">
                <Edit2 size={18} style={{ color: primaryColor }} />
                Renommer la colonne
              </h3>
              <button onClick={() => setShowEditColumnModal(false)} className="p-1 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800">
                <X size={18} className="text-slate-500" />
              </button>
            </div>
            <input
              type="text"
              value={editingColumnName}
              onChange={(e) => setEditingColumnName(e.target.value)}
              placeholder="Nouveau nom"
              className="input-glass w-full mb-4"
              autoFocus
              onKeyDown={(e) => { if (e.key === 'Enter') confirmEditColumn(); }}
            />
            <div className="flex gap-2">
              <button onClick={() => setShowEditColumnModal(false)} className="btn-glass flex-1">Annuler</button>
              <button onClick={confirmEditColumn} className="btn-primary flex-1">Renommer</button>
            </div>
          </div>
        </div>
      )}

      {/* Items Modal */}
      {showItemsModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm" onClick={() => setShowItemsModal(false)}>
          <div className="glass-card w-96 max-h-[80vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
            <h3 className="font-bold mb-4 flex items-center gap-2">
              <List size={18} style={{ color: primaryColor }} />
              Items existants
            </h3>
            <p className="text-xs text-slate-500 mb-3">Sélectionnez les items à ajouter :</p>
            <div className="space-y-2 max-h-60 overflow-y-auto">
              {availableItems.length === 0 ? (
                <p className="text-center text-slate-400 py-4 italic">Aucun item disponible</p>
              ) : (
                availableItems.map((item, i) => (
                  <label key={i} className="flex items-center gap-3 p-3 hover:bg-slate-50 dark:hover:bg-slate-800/30 rounded-lg cursor-pointer transition-colors">
                    <input type="checkbox" value={item} className="rounded accent-cyan-500" id={`item-${i}`} />
                    <span className="text-sm">{item}</span>
                  </label>
                ))
              )}
            </div>
            <div className="flex gap-2 mt-6">
              <button onClick={() => { setShowItemsModal(false); finalizeTable(['Description'], []); }} className="btn-glass flex-1">Passer</button>
              <button onClick={() => {
                const checked = Array.from(document.querySelectorAll('input[id^="item-"]:checked')).map(cb => cb.value);
                if (checked.length === 0) { finalizeTable(['Description'], []); setShowItemsModal(false); } 
                else { promptCols(checked); }
              }} className="btn-primary flex-1">{availableCols.length > 0 ? 'Étape suivante' : 'Terminer'}</button>
            </div>
          </div>
        </div>
      )}

      {/* Columns Modal */}
      {showColsModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm" onClick={() => setShowColsModal(false)}>
          <div className="glass-card w-96" onClick={e => e.stopPropagation()}>
            <h3 className="font-bold mb-4 flex items-center gap-2">
              <Columns size={18} style={{ color: primaryColor }} />
              Colonnes à afficher
            </h3>
            <p className="text-xs text-slate-500 mb-3">Sélectionnez les colonnes :</p>
            <div className="space-y-2 max-h-60 overflow-y-auto">
              {availableCols.length === 0 ? (
                <p className="text-center text-slate-400 py-4 italic">Aucune colonne disponible</p>
              ) : (
                availableCols.map((col, i) => (
                  <label key={i} className={`flex items-center gap-3 p-2 rounded-lg ${col === 'Description' ? 'bg-slate-50 dark:bg-slate-800/30' : 'hover:bg-slate-50 dark:hover:bg-slate-800/30 cursor-pointer'}`}>
                    <input type="checkbox" value={col} defaultChecked disabled={col === 'Description'} className="rounded accent-cyan-500" id={`col-${i}`} />
                    <span className="text-sm">{col}</span>
                    {col === 'Description' && <span className="text-xs text-slate-400 ml-auto">(obligatoire)</span>}
                  </label>
                ))
              )}
            </div>
            <div className="flex gap-2 mt-6">
              <button onClick={() => setShowColsModal(false)} className="btn-glass flex-1">Retour</button>
              <button onClick={() => {
                const checked = Array.from(document.querySelectorAll('input[id^="col-"]:checked')).map(cb => cb.value);
                finalizeTable(checked.length ? checked : ['Description'], selectedItems);
              }} className="btn-primary flex-1">Terminer</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}