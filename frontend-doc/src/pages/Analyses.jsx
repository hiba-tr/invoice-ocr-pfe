import { useState, useEffect } from 'react';
import { apiCall } from '../api/api';
import { Line, Doughnut } from 'react-chartjs-2';
import 'chart.js/auto';
import { Download, AlertTriangle, Grid, PieChart } from 'lucide-react';

export default function Analyses() {
  const [concessions, setConcessions] = useState([]);
  const [selectedConcession, setSelectedConcession] = useState('');
  const [annee, setAnnee] = useState(new Date().getFullYear().toString());
  const [activeTab, setActiveTab] = useState('overview');
  const [data, setData] = useState(null);

  const currentYear = new Date().getFullYear();
  const years = Array.from({ length: currentYear - 2019 }, (_, i) => currentYear - i);

  useEffect(() => {
    apiCall('GET', '/concessions').then(setConcessions).catch(console.error);
  }, []);

  useEffect(() => {
    if (selectedConcession && annee) {
      apiCall('GET', '/analyses/comparaison', null, { id_concession: selectedConcession, annee })
        .then(setData)
        .catch(console.error);
    }
  }, [selectedConcession, annee]);

  const handleExportExcel = () => {
    if (!selectedConcession) {
      alert("Sélectionnez une concession d'abord.");
      return;
    }
    const params = new URLSearchParams({ id_concession: selectedConcession, annee });
    window.open(`http://localhost:8000/analyses/export-excel?${params.toString()}`, '_blank');
  };

  // Configurations des graphiques (couleurs modernes)
  const palette = ['#8b5cf6', '#3b82f6', '#06b6d4', '#10b981', '#f59e0b', '#ef4444', '#ec4899'];

  const lineChart = {
    labels: ['Jan', 'Fév', 'Mar', 'Avr', 'Mai', 'Juin', 'Juil', 'Août', 'Sep', 'Oct', 'Nov', 'Déc'],
    datasets: [{
      label: 'Dépenses mensuelles',
      data: data?.totaux_mensuels || Array(12).fill(0),
      borderColor: '#8b5cf6', backgroundColor: 'rgba(139, 92, 246, 0.1)', fill: true, tension: 0.4
    }]
  };

  // Simulation des données pour Donut et Trimestre (à adapter selon votre API réelle)
  const donutChart = {
    labels: data?.articles_comparaison?.slice(0, 5).map(a => a.article) || ['Aucune donnée'],
    datasets: [{
      data: data?.articles_comparaison?.slice(0, 5).map(a => a.occurrences) || [1],
      backgroundColor: palette
    }]
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row justify-between items-center gap-4 bg-white dark:bg-slate-900 p-4 rounded-xl border border-violet-200 dark:border-slate-800 shadow-sm">
        <h2 className="text-2xl font-bold text-violet-900 dark:text-white flex items-center gap-2">
          <PieChart className="text-primaryLight dark:text-cyan-400" /> Dashboard Analytique
        </h2>
        <div className="flex gap-3">
          <select value={selectedConcession} onChange={(e) => setSelectedConcession(e.target.value)} className="bg-violet-50 dark:bg-slate-800 border border-violet-200 dark:border-slate-700 p-2 rounded-lg outline-none">
            <option value="">-- Concession --</option>
            {concessions.map(c => <option key={c.id_concession} value={c.id_concession}>{c.nom}</option>)}
          </select>
          <select value={annee} onChange={(e) => setAnnee(e.target.value)} className="bg-violet-50 dark:bg-slate-800 border border-violet-200 dark:border-slate-700 p-2 rounded-lg outline-none">
            {years.map(y => <option key={y} value={y}>{y}</option>)}
          </select>
          <button onClick={handleExportExcel} className="bg-green-600 hover:bg-green-700 text-white px-4 py-2 rounded-lg flex items-center gap-2 transition">
            <Download size={18} /> Excel
          </button>
        </div>
      </div>

      {/* Navigation des onglets (identique à analyses.html) */}
      <div className="flex border-b border-violet-200 dark:border-slate-800 mb-6">
        {[
          { id: 'overview', label: 'Vue d\'ensemble', icon: <PieChart size={16}/> },
          { id: 'anomalies', label: 'Alertes & Anomalies', icon: <AlertTriangle size={16}/> },
          { id: 'heatmap', label: 'Heatmap Dépenses', icon: <Grid size={16}/> }
        ].map(tab => (
          <button key={tab.id} onClick={() => setActiveTab(tab.id)} className={`flex items-center gap-2 px-6 py-3 font-medium transition-colors ${activeTab === tab.id ? 'text-primaryLight dark:text-cyan-400 border-b-2 border-primaryLight dark:border-cyan-400' : 'text-slate-500 hover:text-slate-800 dark:hover:text-white'}`}>
            {tab.icon} {tab.label}
          </button>
        ))}
      </div>

      {data ? (
        <div className="space-y-6">
          {activeTab === 'overview' && (
            <>
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                <div className="lg:col-span-2 bg-white dark:bg-slate-900 p-6 rounded-xl border border-violet-200 dark:border-slate-800 shadow-sm h-80">
                  <h3 className="font-bold mb-4 text-slate-800 dark:text-white">Évolution Mensuelle</h3>
                  <Line data={lineChart} options={{ maintainAspectRatio: false }} />
                </div>
                <div className="bg-white dark:bg-slate-900 p-6 rounded-xl border border-violet-200 dark:border-slate-800 shadow-sm h-80 flex flex-col items-center">
                  <h3 className="font-bold mb-4 text-slate-800 dark:text-white w-full">Top Catégories</h3>
                  <div className="flex-1 w-full relative"><Doughnut data={donutChart} options={{ maintainAspectRatio: false }} /></div>
                </div>
              </div>

              <div className="bg-white dark:bg-slate-900 p-6 rounded-xl border border-violet-200 dark:border-slate-800 shadow-sm">
                <h3 className="font-bold mb-4 text-slate-800 dark:text-white">Comparaison des prix par article</h3>
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-sm">
                    <thead>
                      <tr className="border-b border-violet-200 dark:border-slate-800 text-slate-500">
                        <th className="pb-3">Article</th>
                        <th className="pb-3 text-center">Occurrences</th>
                        <th className="pb-3 text-right">Prix Moyen</th>
                        <th className="pb-3 text-right">Prix Min</th>
                        <th className="pb-3 text-right">Prix Max</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.articles_comparaison?.map((art, idx) => (
                        <tr key={idx} className="border-b border-violet-100 dark:border-slate-800/50">
                          <td className="py-3 font-medium text-slate-800 dark:text-white">{art.article}</td>
                          <td className="py-3 text-center">{art.occurrences}</td>
                          <td className="py-3 text-right font-bold text-primaryLight dark:text-cyan-400">{art.prix_moyen?.toFixed(2)} €</td>
                          <td className="py-3 text-right text-green-600 dark:text-green-400">{art.prix_min?.toFixed(2)} €</td>
                          <td className="py-3 text-right text-red-600 dark:text-red-400">{art.prix_max?.toFixed(2)} €</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </>
          )}

          {activeTab === 'anomalies' && (
            <div className="bg-white dark:bg-slate-900 p-6 rounded-xl border border-violet-200 dark:border-slate-800 shadow-sm">
               <h3 className="font-bold mb-4 text-slate-800 dark:text-white flex items-center gap-2"><AlertTriangle className="text-yellow-500"/> Alertes détectées</h3>
               <div className="bg-yellow-50 dark:bg-yellow-900/20 text-yellow-800 dark:text-yellow-200 p-4 rounded-lg border border-yellow-200 dark:border-yellow-700/50">
                 Fonctionnalité d'anomalies en cours d'intégration avec l'API...
               </div>
            </div>
          )}

          {activeTab === 'heatmap' && (
            <div className="bg-white dark:bg-slate-900 p-6 rounded-xl border border-violet-200 dark:border-slate-800 shadow-sm">
               <h3 className="font-bold mb-4 text-slate-800 dark:text-white flex items-center gap-2"><Grid className="text-primaryLight"/> Heatmap des dépenses</h3>
               <div className="bg-slate-50 dark:bg-slate-800 p-8 rounded-lg text-center text-slate-500">
                 Heatmap D3.js en cours de rendu...
               </div>
            </div>
          )}
        </div>
      ) : (
        <div className="bg-white dark:bg-slate-900 p-12 rounded-xl border border-dashed border-violet-300 dark:border-slate-700 text-center text-slate-500">
          Sélectionnez une concession et une année pour afficher les analyses.
        </div>
      )}
    </div>
  );
}