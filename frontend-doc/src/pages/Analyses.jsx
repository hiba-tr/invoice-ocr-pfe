import { useState, useEffect, useCallback } from 'react';
import { useApp } from '../context/AppContext';
import { apiCall } from '../api/api';
import {
  Chart as ChartJS, CategoryScale, LinearScale, PointElement, LineElement,
  BarElement, ArcElement, Tooltip, Legend, Filler
} from 'chart.js';
import { Line, Doughnut, Bar } from 'react-chartjs-2';
import {
  PieChart, AlertTriangle, Filter, 
  TrendingDown, TrendingUp as TrendingUpIcon, Calendar,
  DollarSign, ShoppingCart, Award, FileText, AlertCircle
} from 'lucide-react';

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, BarElement, ArcElement, Tooltip, Legend, Filler);

const PALETTE = ['#3de8f4', '#5b8af7', '#f472b6', '#34d399', '#fbbf24', '#a78bfa', '#fb7185', '#38bdf8'];
const MONTHS = ['Jan', 'Fév', 'Mar', 'Avr', 'Mai', 'Juin', 'Juil', 'Août', 'Sep', 'Oct', 'Nov', 'Déc'];
const primaryColor = '#06b6d4';

const formatMoney = (v) => {
  if (v === null || v === undefined) return '—';
  return new Intl.NumberFormat('fr-FR', { style: 'currency', currency: 'EUR', minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(v);
};

const formatNumber = (v) => {
  if (v === null || v === undefined) return '—';
  return new Intl.NumberFormat('fr-FR').format(v);
};

export default function Analyses() {
  const { showSpinner, hideSpinner, showToast, concessionsList } = useApp();
  const [selectedConcession, setSelectedConcession] = useState('');
  const [annee, setAnnee] = useState(new Date().getFullYear().toString());
  const [mois, setMois] = useState('');
  const [data, setData] = useState(null);
  const [chartType, setChartType] = useState('line');
  const [hoveredBar, setHoveredBar] = useState(null);
  const [ setHoveredDonut] = useState(null);

  const years = Array.from({ length: new Date().getFullYear() - 2019 }, (_, i) => new Date().getFullYear() - i);

  useEffect(() => {
    apiCall('GET', '/concessions').catch(() => {});
  }, []);

  const lancerAnalyse = useCallback(async () => {
    if (!selectedConcession) {
      showToast('Sélectionnez une concession', 'warning');
      return;
    }
    showSpinner();
    try {
      const params = { id_concession: parseInt(selectedConcession), annee: parseInt(annee) };
      if (mois) params.mois = parseInt(mois);
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

  const totalFacture = data?.kpi?.total_facture || 0;
  const nbFactures = data?.kpi?.nb_factures || 0;
  const panierMoyen = data?.kpi?.panier_moyen || 0;
  const topArticle = data?.kpi?.top_article || '—';
  const evolutionGlobale = data?.evolution_globale || 0;
  const meilleurMois = data?.meilleur_mois || { mois: '—', montant: 0 };
  const moisFaible = data?.mois_faible || { mois: '—', montant: 0 };

  const lineData = {
    labels: MONTHS,
    datasets: [
      {
        label: annee,
        data: data?.totaux_mensuels || Array(12).fill(0),
        borderColor: primaryColor,
        backgroundColor: (context) => {
          const chart = context.chart;
          const { ctx, chartArea } = chart;
          if (!chartArea) return null;
          const gradient = ctx.createLinearGradient(0, chartArea.top, 0, chartArea.bottom);
          gradient.addColorStop(0, `${primaryColor}40`);
          gradient.addColorStop(1, `${primaryColor}02`);
          return gradient;
        },
        fill: true,
        tension: 0.4,
        pointRadius: 4,
        pointHoverRadius: 7,
        pointBackgroundColor: primaryColor,
        pointBorderColor: 'white',
        pointBorderWidth: 2,
      },
      data?.comparaison_n1 && {
        label: String(parseInt(annee) - 1),
        data: data.comparaison_n1.totaux_mensuels,
        borderColor: '#94a3b8',
        borderDash: [6, 4],
        fill: false,
        tension: 0.4,
        pointRadius: 3,
        pointBackgroundColor: '#94a3b8',
        pointBorderColor: 'white',
        pointBorderWidth: 2,
      }
    ].filter(Boolean),
  };

  const donutData = {
    labels: data?.repartition_articles?.slice(0, 5).map(r => r.article) || ['Aucune'],
    datasets: [{
      data: data?.repartition_articles?.slice(0, 5).map(r => r.montant) || [1],
      backgroundColor: PALETTE,
      borderColor: 'transparent',
      borderWidth: 3,
      hoverOffset: 15,
    }],
  };

  const donutOptions = {
    responsive: true,
    maintainAspectRatio: false,
    cutout: '65%',
    plugins: {
      legend: { 
        position: 'bottom', 
        labels: { 
          color: '#64748b', 
          font: { size: 10, family: 'JetBrains Mono' }, 
          boxWidth: 10,
          usePointStyle: true,
          pointStyle: 'circle'
        } 
      },
      tooltip: { 
        callbacks: { 
          label: (ctx) => {
            const value = ctx.raw;
            const total = donutData.datasets[0].data.reduce((a, b) => a + b, 0);
            const percentage = ((value / total) * 100).toFixed(1);
            return `${ctx.label}: ${formatMoney(value)} (${percentage}%)`;
          }
        } 
      }
    },
    onHover: (event, activeElements) => {
      if (activeElements.length > 0) {
        setHoveredDonut(activeElements[0].dataIndex);
      } else {
        setHoveredDonut(null);
      }
    }
  };

  const barData = {
    labels: ['T1', 'T2', 'T3', 'T4'],
    datasets: [{
      label: annee,
      data: data?.totaux_mensuels
        ? [0, 1, 2, 3].map(t => data.totaux_mensuels.slice(t * 3, t * 3 + 3).reduce((a, b) => a + b, 0))
        : [0, 0, 0, 0],
      backgroundColor: (context) => {
        const index = context.dataIndex;
        return hoveredBar === index ? primaryColor : `${primaryColor}70`;
      },
      borderRadius: 8,
      barPercentage: 0.65,
      categoryPercentage: 0.8,
      hoverBackgroundColor: primaryColor,
    }],
  };

  const barOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      tooltip: { callbacks: { label: (ctx) => `${ctx.dataset.label}: ${formatMoney(ctx.raw)}` } }
    },
    onHover: (event, activeElements) => {
      if (activeElements.length > 0) {
        setHoveredBar(activeElements[0].dataIndex);
      } else {
        setHoveredBar(null);
      }
    }
  };

  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: { 
      legend: { 
        display: true, 
        position: 'top',
        labels: { color: '#64748b', font: { family: 'JetBrains Mono', size: 11 }, usePointStyle: true } 
      },
      tooltip: { callbacks: { label: (ctx) => `${ctx.dataset.label}: ${formatMoney(ctx.raw)}` } }
    },
    scales: {
      x: { grid: { display: false }, ticks: { color: '#64748b', font: { size: 10 } } },
      y: { grid: { color: 'rgba(148, 163, 184, 0.1)' }, ticks: { color: '#64748b', callback: (v) => formatMoney(v), font: { size: 10 } } },
    },
    interaction: { mode: 'index', intersect: false },
  };

  const anomaliesList = (data?.anomalies || []).filter(a => !a.toLowerCase().includes('aucune'));

  return (
    <div className="max-w-7xl mx-auto space-y-6 animate-fade-in">
      {/* Header */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <div className="flex items-center gap-2 text-xs font-mono uppercase tracking-wider mb-1" style={{ color: primaryColor }}>
            <span className="w-6 h-px" style={{ background: primaryColor }} />
            Intelligence Analytique
          </div>
          <h1 className="font-display text-3xl font-extrabold text-slate-800 dark:text-white">
            Analyses & <span style={{ color: primaryColor }}>Insights</span>
          </h1>
          <p className="text-slate-500 dark:text-slate-400 text-sm mt-1">
            Suivez vos performances et prenez des décisions éclairées.
          </p>
        </div>
        <div className="flex items-center gap-2 px-4 py-2 rounded-full glass border-emerald-200 dark:border-emerald-500/20">
          <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
          <span className="text-xs font-mono text-emerald-700 dark:text-emerald-400">Données temps réel</span>
        </div>
      </div>

      {/* Filtres */}
      <div className="glass-card">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 items-end">
          <div>
            <label className="block text-xs font-mono uppercase tracking-wider text-slate-500 mb-2">Concession</label>
            <select value={selectedConcession} onChange={(e) => setSelectedConcession(e.target.value)} className="select-glass input-glass">
              <option value="">— Sélectionner —</option>
              {concessionsList.map(c => (
                <option key={c.id_concession} value={c.id_concession}>{c.nom}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs font-mono uppercase tracking-wider text-slate-500 mb-2">Année</label>
            <select value={annee} onChange={(e) => setAnnee(e.target.value)} className="select-glass input-glass">
              {years.map(y => <option key={y} value={y}>{y}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-xs font-mono uppercase tracking-wider text-slate-500 mb-2">Mois (optionnel)</label>
            <select value={mois} onChange={(e) => setMois(e.target.value)} className="select-glass input-glass">
              <option value="">Tous les mois</option>
              {MONTHS.map((m, i) => <option key={i} value={i + 1}>{m}</option>)}
            </select>
          </div>
          <div className="flex gap-2">
            <button onClick={lancerAnalyse} className="btn-primary text-sm py-2.5 flex-1">
              <Filter size={16} /> Analyser
            </button>
            <button onClick={handleExportExcel} className="btn-glass text-sm" style={{ color: primaryColor }}>
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
          {/* KPI Cards - 5 cartes comme sur l'image */}
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
            <div className="glass-card p-4 text-center relative overflow-hidden">
              <div className="absolute top-0 left-0 w-1 h-full bg-cyan-500 rounded-l-lg" />
              <div className="flex items-center justify-center gap-2 mb-2">
                <DollarSign size={20} className="text-cyan-500" />
                <span className="kpi-label">Total facturé</span>
              </div>
              <p className="font-display text-2xl font-bold text-slate-800 dark:text-white">{formatMoney(totalFacture)}</p>
              {evolutionGlobale !== 0 && (
                <p className={`text-xs mt-1 flex items-center justify-center gap-1 ${evolutionGlobale > 0 ? 'text-emerald-500' : 'text-red-500'}`}>
                  {evolutionGlobale > 0 ? <TrendingUpIcon size={12} /> : <TrendingDown size={12} />}
                  {Math.abs(evolutionGlobale).toFixed(1)}% vs {parseInt(annee) - 1}
                </p>
              )}
            </div>
            <div className="glass-card p-4 text-center relative overflow-hidden">
              <div className="absolute top-0 left-0 w-1 h-full bg-blue-500 rounded-l-lg" />
              <div className="flex items-center justify-center gap-2 mb-2">
                <FileText size={20} className="text-blue-500" />
                <span className="kpi-label">Nombre de factures</span>
              </div>
              <p className="font-display text-2xl font-bold text-slate-800 dark:text-white">{formatNumber(nbFactures)}</p>
            </div>
            <div className="glass-card p-4 text-center relative overflow-hidden">
              <div className="absolute top-0 left-0 w-1 h-full bg-pink-500 rounded-l-lg" />
              <div className="flex items-center justify-center gap-2 mb-2">
                <ShoppingCart size={20} className="text-pink-500" />
                <span className="kpi-label">Panier moyen</span>
              </div>
              <p className="font-display text-2xl font-bold text-slate-800 dark:text-white">{formatMoney(panierMoyen)}</p>
            </div>
            <div className="glass-card p-4 text-center relative overflow-hidden">
              <div className="absolute top-0 left-0 w-1 h-full bg-emerald-500 rounded-l-lg" />
              <div className="flex items-center justify-center gap-2 mb-2">
                <Award size={20} className="text-emerald-500" />
                <span className="kpi-label">Top article</span>
              </div>
              <p className="font-display text-sm font-bold text-slate-800 dark:text-white truncate">{topArticle}</p>
            </div>
            <div className="glass-card p-4 text-center relative overflow-hidden">
              <div className="absolute top-0 left-0 w-1 h-full bg-amber-500 rounded-l-lg" />
              <div className="flex items-center justify-center gap-2 mb-2">
                <AlertCircle size={20} className="text-amber-500" />
                <span className="kpi-label">Anomalies</span>
              </div>
              <p className="font-display text-2xl font-bold text-amber-500">{anomaliesList.length}</p>
            </div>
          </div>

          {/* Graphiques principaux */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="lg:col-span-2 glass-card p-4">
              <div className="flex justify-between items-center mb-4">
                <h3 className="font-display font-bold text-slate-800 dark:text-white">Évolution mensuelle des ventes</h3>
                <div className="flex gap-1 bg-slate-100 dark:bg-slate-800 rounded-lg p-1">
                  <button onClick={() => setChartType('line')} className={`px-3 py-1 rounded-md text-xs font-mono transition-all ${chartType === 'line' ? 'bg-cyan-500 text-white' : 'text-slate-500'}`}>Ligne</button>
                  <button onClick={() => setChartType('bar')} className={`px-3 py-1 rounded-md text-xs font-mono transition-all ${chartType === 'bar' ? 'bg-cyan-500 text-white' : 'text-slate-500'}`}>Barres</button>
                </div>
              </div>
              <div className="h-72">{chartType === 'line' ? <Line data={lineData} options={chartOptions} /> : <Bar data={lineData} options={chartOptions} />}</div>
            </div>
            <div className="glass-card p-4">
              <h3 className="font-display font-bold mb-4 text-slate-800 dark:text-white">Répartition par article</h3>
              <div className="h-52"><Doughnut data={donutData} options={donutOptions} /></div>
              {data.repartition_articles?.length > 0 && (
                <p className="text-xs text-slate-400 mt-4 text-center">
                  Total: {formatMoney(totalFacture)} • {data.repartition_articles.length} article(s)
                </p>
              )}
            </div>
          </div>

          {/* Dépenses par trimestre + Comparaison */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="glass-card p-4">
              <h3 className="font-display font-bold mb-4 text-slate-800 dark:text-white">Dépenses par trimestre</h3>
              <div className="h-64"><Bar data={barData} options={barOptions} /></div>
            </div>
            <div className="glass-card p-4">
              <h3 className="font-display font-bold mb-4 flex items-center gap-2 text-slate-800 dark:text-white">
                <TrendingUpIcon size={18} style={{ color: primaryColor }} />
                Comparaison vs N-1
              </h3>
              <div className="flex flex-col items-center justify-center h-48">
                <p className={`text-5xl font-bold ${evolutionGlobale > 0 ? 'text-emerald-500' : 'text-red-500'}`}>
                  {evolutionGlobale > 0 ? '+' : ''}{evolutionGlobale.toFixed(1)}%
                </p>
                <p className="text-sm text-slate-500 mt-2">vs {parseInt(annee) - 1}</p>
                <p className="text-xs text-slate-400 mt-4">Évolution globale</p>
              </div>
            </div>
          </div>

          {/* Alertes récentes */}
          <div className="glass-card p-4">
            <h3 className="font-display font-bold mb-4 flex items-center gap-2 text-slate-800 dark:text-white">
              <AlertTriangle className="text-amber-500" size={18} />
              Alertes récentes
            </h3>
            {anomaliesList.length === 0 ? (
              <div className="flex items-center gap-3 p-4 bg-emerald-50 dark:bg-emerald-500/10 rounded-xl border-l-4 border-emerald-500">
                <span className="text-xl">✅</span>
                <p className="text-sm text-emerald-800 dark:text-emerald-300">Aucune anomalie détectée.</p>
              </div>
            ) : (
              <div className="space-y-3">
                {anomaliesList.slice(0, 5).map((a, i) => (
                  <div key={i} className="flex items-start gap-3 p-3 bg-amber-50 dark:bg-amber-500/10 rounded-xl border-l-4 border-amber-500">
                    <span className="text-lg">⚠️</span>
                    <p className="text-sm text-amber-800 dark:text-amber-300">{a}</p>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Faits marquants */}
          <div className="glass-card p-4">
            <h3 className="font-display font-bold mb-4 flex items-center gap-2 text-slate-800 dark:text-white">
              <Calendar size={18} style={{ color: primaryColor }} />
              Faits marquants
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="flex items-center justify-between p-4 bg-slate-50 dark:bg-slate-800/30 rounded-xl">
                <div>
                  <p className="text-xs text-slate-500">🏆 Meilleur mois</p>
                  <p className="font-semibold text-slate-800 dark:text-white">{meilleurMois.mois}</p>
                </div>
                <p className="font-bold text-emerald-500">{formatMoney(meilleurMois.montant)}</p>
              </div>
              <div className="flex items-center justify-between p-4 bg-slate-50 dark:bg-slate-800/30 rounded-xl">
                <div>
                  <p className="text-xs text-slate-500">📉 Mois le plus faible</p>
                  <p className="font-semibold text-slate-800 dark:text-white">{moisFaible.mois}</p>
                </div>
                <p className="font-bold text-red-500">{formatMoney(moisFaible.montant)}</p>
              </div>
            </div>
          </div>

          {/* Tableau des articles */}
          <div className="glass-card p-4">
            <h3 className="font-display font-bold text-lg text-slate-800 dark:text-white mb-4">
              Articles - Comparaison des prix
            </h3>
            <div className="overflow-x-auto rounded-xl border border-slate-200/30 dark:border-slate-700/30">
              {data.articles_comparaison?.length === 0 ? (
                <p className="text-center text-slate-400 dark:text-slate-500 py-10 italic">
                  Aucune donnée d'article disponible
                </p>
              ) : (
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-gradient-to-r from-blue-50/80 to-cyan-50/80 dark:from-blue-950/30 dark:to-cyan-950/20">
                      <th className="px-4 py-3 text-left font-mono text-xs uppercase tracking-wider" style={{ color: primaryColor }}>Article</th>
                      <th className="px-4 py-3 text-center font-mono text-xs uppercase tracking-wider" style={{ color: primaryColor }}>Occ.</th>
                      <th className="px-4 py-3 text-right font-mono text-xs uppercase tracking-wider" style={{ color: primaryColor }}>Prix moyen</th>
                      <th className="px-4 py-3 text-right font-mono text-xs uppercase tracking-wider" style={{ color: primaryColor }}>Min</th>
                      <th className="px-4 py-3 text-right font-mono text-xs uppercase tracking-wider" style={{ color: primaryColor }}>Max</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-blue-100/50 dark:divide-slate-800/50">
                    {data.articles_comparaison?.slice(0, 10).map((art, idx) => (
                      <tr key={idx} className="hover:bg-blue-50/30 dark:hover:bg-slate-800/30 transition-colors">
                        <td className="px-4 py-3 font-medium text-slate-800 dark:text-slate-200 whitespace-nowrap">{art.article}</td>
                        <td className="px-4 py-3 text-center text-slate-600 dark:text-slate-400">
                          <span className="badge-status bg-cyan-50 dark:bg-cyan-950/30 text-cyan-600 dark:text-cyan-400 px-2 py-0.5 rounded-full text-xs">
                            {art.occurrences}
                          </span>
                        </td>
                        <td className="px-4 py-3 font-mono text-right text-slate-600 dark:text-slate-400">{formatMoney(art.prix_moyen)}</td>
                        <td className="px-4 py-3 font-mono text-right text-slate-600 dark:text-slate-400">{formatMoney(art.prix_min)}</td>
                        <td className="px-4 py-3 font-mono text-right text-slate-600 dark:text-slate-400">{formatMoney(art.prix_max)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
            <p className="text-right text-xs font-mono text-slate-400 dark:text-slate-500 mt-4">
              {data.articles_comparaison?.length || 0} article(s) analysé(s)
            </p>
          </div>
        </>
      )}
    </div>
  );
}