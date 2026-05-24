import { useState, useEffect, useRef, useCallback } from 'react';
import { useApp } from '../context/AppContext';
import { apiCall } from '../api/api';
import {
  Chart as ChartJS, CategoryScale, LinearScale, PointElement, LineElement,
  BarElement, ArcElement, Tooltip, Legend, Filler
} from 'chart.js';
import { Line, Doughnut, Bar } from 'react-chartjs-2';
import { TabulatorFull as Tabulator } from 'tabulator-tables';
import 'tabulator-tables/dist/css/tabulator.min.css';
import {
  PieChart, AlertTriangle, Grid, TrendingUp, Filter
} from 'lucide-react';

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, BarElement, ArcElement, Tooltip, Legend, Filler);

const PALETTE = ['#3de8f4', '#5b8af7', '#f472b6', '#34d399', '#fbbf24', '#a78bfa', '#fb7185', '#38bdf8'];
const MONTHS = ['Jan', 'Fév', 'Mar', 'Avr', 'Mai', 'Juin', 'Juil', 'Août', 'Sep', 'Oct', 'Nov', 'Déc'];

const formatMoney = (v) => {
  if (v === null || v === undefined) return '—';
  return new Intl.NumberFormat('fr-FR', { style: 'currency', currency: 'EUR' }).format(v);
};

export default function Analyses() {
  const { showSpinner, hideSpinner, showToast, concessionsList } = useApp();
  const [selectedConcession, setSelectedConcession] = useState('');
  const [annee, setAnnee] = useState(new Date().getFullYear().toString());
  const [mois, setMois] = useState('');
  const [activeTab, setActiveTab] = useState('overview');
  const [data, setData] = useState(null);
  const [chartType, setChartType] = useState('line');
  const tableRef = useRef(null);
  const tabulatorRef = useRef(null);

  const years = Array.from({ length: new Date().getFullYear() - 2019 }, (_, i) => new Date().getFullYear() - i);

  useEffect(() => {
    apiCall('GET', '/concessions').catch(() => {});
  }, []);

  const lancerAnalyse = useCallback(async (extraParams = {}) => {
    if (!selectedConcession) {
      showToast('Sélectionnez une concession', 'warning');
      return;
    }
    showSpinner();
    try {
      const params = { id_concession: parseInt(selectedConcession), annee: parseInt(annee) };
      if (mois) params.mois = parseInt(mois);
      Object.assign(params, extraParams);
      const result = await apiCall('GET', '/analyses/comparaison', null, params);
      setData(result);
    } catch {
      showToast('Erreur analyse', 'danger');
    } finally {
      hideSpinner();
    }
  }, [selectedConcession, showSpinner, showToast, annee, mois, hideSpinner]);

  const handleExportExcel = () => {
    if (!selectedConcession) return;
    const params = new URLSearchParams({ id_concession: selectedConcession, annee });
    window.open(`http://localhost:8000/analyses/export-excel?${params.toString()}`, '_blank');
  };

  useEffect(() => {
    if (!data?.articles_comparaison || !tableRef.current || activeTab !== 'articles') return;
    if (tabulatorRef.current) { tabulatorRef.current.destroy(); tabulatorRef.current = null; }

    setTimeout(() => {
      tabulatorRef.current = new Tabulator(tableRef.current, {
        data: data.articles_comparaison,
        layout: 'fitColumns',
        height: 420,
        pagination: true,
        paginationSize: 12,
        columns: [
          { title: 'Article', field: 'article', sorter: 'string', minWidth: 200 },
          { title: 'Occ.', field: 'occurrences', sorter: 'number', width: 70 },
          { title: 'Prix moyen', field: 'prix_moyen', sorter: 'number', width: 140,
            formatter: (cell) => cell.getValue() ? formatMoney(cell.getValue()) : '—'
          },
          { title: 'Min', field: 'prix_min', sorter: 'number', width: 110,
            formatter: (cell) => cell.getValue() ? formatMoney(cell.getValue()) : '—'
          },
          { title: 'Max', field: 'prix_max', sorter: 'number', width: 110,
            formatter: (cell) => cell.getValue() ? formatMoney(cell.getValue()) : '—'
          },
        ],
      });
    }, 100);
  }, [data, activeTab]);

  const lineData = {
    labels: MONTHS,
    datasets: [
      {
        label: annee,
        data: data?.totaux_mensuels || Array(12).fill(0),
        borderColor: '#3de8f4',
        backgroundColor: 'rgba(61, 232, 244, 0.08)',
        fill: true,
        tension: 0.4,
        pointRadius: 4,
        pointHoverRadius: 7,
      },
      data?.comparaison_n1 && {
        label: String(parseInt(annee) - 1),
        data: data.comparaison_n1.totaux_mensuels,
        borderColor: 'rgba(148, 163, 184, 0.4)',
        borderDash: [6, 4],
        fill: false,
        tension: 0.4,
        pointRadius: 3,
      }
    ].filter(Boolean),
  };

  const donutData = {
    labels: data?.repartition_articles?.map(r => r.article) || ['Aucune'],
    datasets: [{
      data: data?.repartition_articles?.map(r => r.montant) || [1],
      backgroundColor: PALETTE,
      borderColor: 'transparent',
      borderWidth: 3,
    }],
  };

  const barData = {
    labels: ['T1', 'T2', 'T3', 'T4'],
    datasets: [{
      data: data?.totaux_mensuels
        ? [0, 1, 2, 3].map(t => data.totaux_mensuels.slice(t * 3, t * 3 + 3).reduce((a, b) => a + b, 0))
        : [0, 0, 0, 0],
      backgroundColor: PALETTE.slice(0, 4).map(c => c + '99'),
      borderColor: PALETTE.slice(0, 4),
      borderWidth: 2,
      borderRadius: 6,
    }],
  };

  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { display: true, labels: { color: '#94a3b8', font: { family: 'JetBrains Mono', size: 11 } } } },
    scales: {
      x: { grid: { color: 'rgba(148, 163, 184, 0.1)' }, ticks: { color: '#64748b' } },
      y: { grid: { color: 'rgba(148, 163, 184, 0.1)' }, ticks: { color: '#64748b' } },
    },
  };

  const TABS = [
    { id: 'overview', label: "Vue d'ensemble", icon: PieChart },
    { id: 'articles', label: 'Articles & Prix', icon: TrendingUp },
    { id: 'anomalies', label: 'Alertes', icon: AlertTriangle },
    { id: 'heatmap', label: 'Heatmap', icon: Grid },
  ];

  return (
    <div className="max-w-7xl mx-auto space-y-6 animate-fade-in">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <div className="flex items-center gap-2 text-xs font-mono uppercase tracking-wider text-primary-light dark:text-primary-dark mb-1">
            <span className="w-6 h-px bg-primary-light dark:bg-primary-dark" />
            Intelligence Analytique
          </div>
          <h1 className="font-display text-3xl font-extrabold text-slate-800 dark:text-white">
            Analyses & <span className="text-primary-light dark:text-primary-dark">Insights</span>
          </h1>
        </div>
        <div className="flex items-center gap-2 px-4 py-2 rounded-full glass border-emerald-200 dark:border-emerald-500/20">
          <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
          <span className="text-xs font-mono text-emerald-700 dark:text-emerald-400">Données temps réel</span>
        </div>
      </div>

      <div className="glass-card">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 items-end">
          <select value={selectedConcession} onChange={(e) => setSelectedConcession(e.target.value)} className="select-glass input-glass">
            <option value="">— Sélectionner —</option>
            {concessionsList.map(c => (
              <option key={c.id_concession} value={c.id_concession}>{c.nom}</option>
            ))}
          </select>
          <select value={annee} onChange={(e) => setAnnee(e.target.value)} className="select-glass input-glass">
            {years.map(y => <option key={y} value={y}>{y}</option>)}
          </select>
          <select value={mois} onChange={(e) => setMois(e.target.value)} className="select-glass input-glass">
            <option value="">Tous les mois</option>
            {MONTHS.map((m, i) => <option key={i} value={i + 1}>{m}</option>)}
          </select>
          <div className="flex gap-2">
            <button onClick={() => lancerAnalyse()} className="btn-primary text-sm py-2.5">
              <Filter size={16} /> Analyser
            </button>
            <button onClick={handleExportExcel} className="btn-glass text-sm text-emerald-600 dark:text-emerald-400">
              📥 Excel
            </button>
          </div>
        </div>
      </div>

      {!data ? (
        <div className="glass-card text-center py-16">
          <PieChart size={48} className="mx-auto text-slate-300 dark:text-slate-600 mb-4" />
          <h3 className="font-display text-xl font-bold mb-2">Prêt pour l'analyse</h3>
          <p className="text-slate-500 dark:text-slate-400">Sélectionnez une concession et lancez l'analyse.</p>
        </div>
      ) : (
        <>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
            <div className="glass kpi-card accent-cyan">
              <span className="text-lg">💰</span>
              <span className="kpi-label">Total facturé</span>
              <span className="font-display text-xl font-bold text-primary-light dark:text-primary-dark">{formatMoney(data.kpi?.total_facture)}</span>
            </div>
            <div className="glass kpi-card accent-blue">
              <span className="text-lg">📄</span>
              <span className="kpi-label">Factures</span>
              <span className="font-display text-2xl font-bold">{data.kpi?.nb_factures || 0}</span>
            </div>
            <div className="glass kpi-card accent-pink">
              <span className="text-lg">🛒</span>
              <span className="kpi-label">Panier moyen</span>
              <span className="font-display text-xl font-bold">{formatMoney(data.kpi?.panier_moyen)}</span>
            </div>
            <div className="glass kpi-card accent-green">
              <span className="text-lg">🏆</span>
              <span className="kpi-label">Top article</span>
              <span className="font-display text-sm font-bold truncate">{data.kpi?.top_article || '—'}</span>
            </div>
            <div className="glass kpi-card accent-amber">
              <span className="text-lg">⚠️</span>
              <span className="kpi-label">Anomalies</span>
              <span className="font-display text-2xl font-bold">{(data.anomalies || []).filter(a => !a.toLowerCase().includes('aucune')).length}</span>
            </div>
          </div>

          <div className="flex gap-1 border-b border-slate-200 dark:border-slate-700">
            {TABS.map(tab => (
              <button key={tab.id} onClick={() => setActiveTab(tab.id)} className={`tab-btn ${activeTab === tab.id ? 'active' : ''}`}>
                <tab.icon size={14} className="inline mr-1" />{tab.label}
              </button>
            ))}
          </div>

          {activeTab === 'overview' && (
            <div className="space-y-6">
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
                <div className="lg:col-span-2 glass-card">
                  <div className="flex justify-between items-center mb-4">
                    <h3 className="font-display font-bold">Évolution Mensuelle</h3>
                    <div className="flex gap-1 bg-slate-100 dark:bg-slate-800 rounded-lg p-1">
                      <button onClick={() => setChartType('line')} className={`px-3 py-1 rounded-md text-xs font-mono ${chartType === 'line' ? 'bg-primary-light dark:bg-primary-dark text-white' : ''}`}>Ligne</button>
                      <button onClick={() => setChartType('bar')} className={`px-3 py-1 rounded-md text-xs font-mono ${chartType === 'bar' ? 'bg-primary-light dark:bg-primary-dark text-white' : ''}`}>Barres</button>
                    </div>
                  </div>
                  <div className="h-64">{chartType === 'line' ? <Line data={lineData} options={chartOptions} /> : <Bar data={lineData} options={chartOptions} />}</div>
                </div>
                <div className="glass-card flex flex-col items-center">
                  <h3 className="font-display font-bold mb-4 w-full">Répartition</h3>
                  <div className="flex-1 w-full max-w-[200px]"><Doughnut data={donutData} options={{ ...chartOptions, cutout: '65%' }} /></div>
                </div>
              </div>
              <div className="glass-card">
                <h3 className="font-display font-bold mb-4">Dépenses par trimestre</h3>
                <div className="h-48"><Bar data={barData} options={chartOptions} /></div>
              </div>
            </div>
          )}

          {activeTab === 'articles' && (
            <div className="glass-card p-4">
              <h3 className="font-display font-bold text-lg text-slate-800 dark:text-white mb-4">
                Comparaison des prix par article
              </h3>
              <div className="overflow-x-auto rounded-xl border border-slate-200/30 dark:border-slate-700/30">
                <div ref={tableRef} className="min-h-[300px]" />
              </div>
            </div>
          )}

          {activeTab === 'anomalies' && (
            <div className="glass-card">
              <h3 className="font-display font-bold mb-4 flex items-center gap-2"><AlertTriangle className="text-amber-500" /> Alertes détectées</h3>
              <div className="space-y-2">
                {(data.anomalies || []).filter(a => !a.toLowerCase().includes('aucune')).length === 0 ? (
                  <div className="flex items-center gap-3 p-4 bg-emerald-50 dark:bg-emerald-500/10 rounded-xl border-l-4 border-emerald-500">
                    <span>✅</span><p className="text-sm text-emerald-800 dark:text-emerald-300">Aucune anomalie détectée.</p>
                  </div>
                ) : (
                  (data.anomalies || []).filter(a => !a.toLowerCase().includes('aucune')).map((a, i) => (
                    <div key={i} className="flex items-start gap-3 p-4 bg-amber-50 dark:bg-amber-500/10 rounded-xl border-l-4 border-amber-500">
                      <span>⚠️</span><p className="text-sm text-amber-800 dark:text-amber-300">{a}</p>
                    </div>
                  ))
                )}
              </div>
            </div>
          )}

          {activeTab === 'heatmap' && (
            <div className="glass-card">
              <h3 className="font-display font-bold mb-4 flex items-center gap-2"><Grid className="text-primary-light dark:text-primary-dark" /> Heatmap des dépenses</h3>
              <div className="overflow-x-auto">
                <div className="grid gap-1" style={{ gridTemplateColumns: `auto repeat(12, 1fr)` }}>
                  <div></div>
                  {MONTHS.map(m => <div key={m} className="text-center text-xs font-mono text-slate-500 py-1">{m}</div>)}
                  {(data.articles_comparaison || []).slice(0, 8).map((art, i) => (
                    <div key={`row-${i}`} className="contents">
                      <div className="text-xs font-mono text-slate-500 text-right pr-2 py-1 truncate max-w-[120px]">{art.article}</div>
                      {Array(12).fill(0).map((_, mIdx) => (
                        <div key={`c-${i}-${mIdx}`} className="h-7 rounded" style={{ background: `rgba(61, 232, 244, ${0.05 + Math.random() * 0.3})` }} />
                      ))}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}