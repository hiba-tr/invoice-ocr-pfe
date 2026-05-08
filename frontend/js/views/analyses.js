/**
 * analyses.js — DocCore Invoice Analytics
 * Interface d'analyse avancée niveau PFE
 * Thème: Dark Slate Premium + Accent Cyan Electric
 */

import { showSpinner, hideSpinner, showToast } from '../app.js';
import { apiCall } from '../api.js';

// ─── Instances Chart.js / Tabulator ───────────────────────────────────────────
let chartMensuel   = null;
let chartDonut     = null;
let chartTrimestre = null;
let tableInstance  = null;

// ─── État local ───────────────────────────────────────────────────────────────
let lastData       = null;   // dernière réponse API
let activeTab      = 'overview';
let chartType      = 'line';  // 'line' | 'bar'

// Palette couleurs partagée
const PALETTE = [
  '#3de8f4','#5b8af7','#f472b6','#34d399',
  '#fbbf24','#a78bfa','#fb7185','#38bdf8',
];

// ─── INIT ─────────────────────────────────────────────────────────────────────
export async function initAnalysesView() {
  // Charger concessions
  await loadConcessions();

  // Remplir années (courante → 2020)
  const selAnnee = document.getElementById('analyse-annee');
  const currentYear = new Date().getFullYear();
  selAnnee.innerHTML = '<option value="">— Année —</option>';
  for (let y = currentYear; y >= 2020; y--) {
    selAnnee.innerHTML += `<option value="${y}"${y === currentYear ? ' selected' : ''}>${y}</option>`;
  }

  // Bouton analyser
  document.getElementById('lancer-analyse')
    ?.addEventListener('click', () => lancerAnalyse());

  // Export Excel
  document.getElementById('export-excel')
    ?.addEventListener('click', exportExcel);

  // Presets de période
  bindPresets();

  // Tabs
  document.querySelectorAll('.an-tab').forEach(tab => {
    tab.addEventListener('click', () => switchTab(tab.dataset.tab));
  });

  // Toggle chart type
  document.querySelectorAll('#chart-type-toggle .toggle-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('#chart-type-toggle .toggle-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      chartType = btn.dataset.type;
      if (lastData) renderChartMensuel(lastData);
    });
  });

  // Recherche articles
  document.getElementById('table-search')
    ?.addEventListener('input', e => {
      if (tableInstance) tableInstance.setFilter('article', 'like', e.target.value);
    });
}

// ─── Chargement des concessions ──────────────────────────────────────────────
async function loadConcessions() {
  const sel = document.getElementById('analyse-concession');
  try {
    const concessions = await apiCall('GET', '/concessions');
    sel.innerHTML = '<option value="">— Sélectionner une concession —</option>';
    concessions.forEach(c => {
      sel.innerHTML += `<option value="${c.id_concession}">${c.nom}</option>`;
    });
  } catch {
    showToast('Erreur chargement des concessions', 'danger');
  }
}

// ─── Presets période ─────────────────────────────────────────────────────────
function bindPresets() {
  document.getElementById('preset-annee')
    ?.addEventListener('click', () => {
      clearPresetActive();
      document.getElementById('preset-annee').classList.add('active');
      document.getElementById('analyse-mois').value = '';
      lancerAnalyse();
    });

  for (let t = 1; t <= 4; t++) {
    document.getElementById(`preset-trim${t}`)
      ?.addEventListener('click', () => {
        clearPresetActive();
        document.getElementById(`preset-trim${t}`).classList.add('active');
        document.getElementById('analyse-mois').value = '';
        lancerAnalyse({ trimestre: t });
      });
  }

  document.getElementById('preset-6m')
    ?.addEventListener('click', () => {
      clearPresetActive();
      document.getElementById('preset-6m').classList.add('active');
      const now = new Date();
      const sixMonthsAgo = new Date(now.getFullYear(), now.getMonth() - 5, 1);
      const dateDebut = sixMonthsAgo.toISOString().slice(0, 10);
      const dateFin   = now.toISOString().slice(0, 10);
      lancerAnalyse({ date_debut: dateDebut, date_fin: dateFin });
    });
}

function clearPresetActive() {
  document.querySelectorAll('.preset-pill').forEach(p => p.classList.remove('active'));
}

// ─── Lancer l'analyse ─────────────────────────────────────────────────────────
async function lancerAnalyse(extraParams = {}) {
  const idConcession = document.getElementById('analyse-concession').value;
  const annee = document.getElementById('analyse-annee').value;
  const mois  = document.getElementById('analyse-mois').value;

  if (!idConcession) { showToast('Veuillez sélectionner une concession', 'warning'); return; }
  if (!annee && !extraParams.date_debut && !extraParams.trimestre) {
    showToast('Veuillez sélectionner une année ou une période', 'warning');
    return;
  }

  // Construire les params
  const params = {};
  if (idConcession) params.id_concession = parseInt(idConcession);
  if (annee && !extraParams.date_debut) params.annee = parseInt(annee);
  if (mois && !extraParams.trimestre && !extraParams.date_debut) params.mois = parseInt(mois);
  Object.assign(params, extraParams);

  // Afficher loading
  document.getElementById('an-welcome').style.display   = 'none';
  document.getElementById('an-results').style.display   = 'none';
  document.getElementById('an-loading').style.display   = 'block';

  // Animation messages loading
  const loadingTexts = [
    'Récupération des factures...',
    'Calcul des KPIs...',
    'Analyse des anomalies...',
    'Construction des graphiques...',
  ];
  let ltIdx = 0;
  const ltEl = document.getElementById('loading-text');
  const ltInterval = setInterval(() => {
    ltIdx = (ltIdx + 1) % loadingTexts.length;
    if (ltEl) ltEl.textContent = loadingTexts[ltIdx];
  }, 700);

  try {
    const data = await apiCall('GET', '/analyses/comparaison', null, params);
    clearInterval(ltInterval);
    document.getElementById('an-loading').style.display = 'none';

    lastData = data;

    if (!data.nb_factures) {
      // Aucune facture trouvée
      document.getElementById('an-welcome').style.display = 'flex';
      document.getElementById('an-welcome').querySelector('.welcome-title').textContent = 'Aucune donnée trouvée';
      document.getElementById('an-welcome').querySelector('.welcome-sub').textContent =
        `Aucune facture pour ${data.concession || 'cette concession'} sur la période ${data.plage?.debut ?? ''} – ${data.plage?.fin ?? ''}.`;
      return;
    }

    afficherResultats(data);

  } catch(e) {
    clearInterval(ltInterval);
    document.getElementById('an-loading').style.display = 'none';
    document.getElementById('an-welcome').style.display = 'flex';
    showToast('Erreur lors de l\'analyse. Vérifiez la connexion API.', 'danger');
    console.error('Analyse error:', e);
  }
}

// ─── Afficher tous les résultats ─────────────────────────────────────────────
function afficherResultats(data) {
  document.getElementById('an-results').style.display = 'block';

  // Summary bar
  document.getElementById('sb-concession').textContent = data.concession || '—';
  document.getElementById('sb-periode').textContent    = `${data.plage.debut} → ${data.plage.fin}`;
  document.getElementById('sb-nb').textContent         = `${data.nb_factures} facture${data.nb_factures > 1 ? 's' : ''}`;

  const evoWrap = document.getElementById('sb-evo-wrap');
  const evoEl   = document.getElementById('sb-evo');
  if (data.comparaison_n1?.evolution_pct !== null && data.comparaison_n1?.evolution_pct !== undefined) {
    const pct = data.comparaison_n1.evolution_pct;
    evoWrap.style.display = '';
    evoEl.textContent     = `${pct >= 0 ? '+' : ''}${pct}%`;
    evoEl.style.color     = pct >= 0 ? 'var(--accent-ok)' : 'var(--accent-danger)';
  } else {
    evoWrap.style.display = 'none';
  }

  // KPIs
  renderKPI(data);

  // Graphiques overview
  renderChartMensuel(data);
  renderChartDonut(data);
  renderChartTrimestre(data);
  renderTopArticlesList(data);

  // Articles table
  renderArticlesTable(data);

  // Anomalies
  renderAnomalies(data);

  // Heatmap
  renderHeatmap(data);

  // Reset tab to overview
  switchTab('overview');
}

// ─── KPI ─────────────────────────────────────────────────────────────────────
function renderKPI(data) {
  const kpi = data.kpi;
  if (!kpi) return;

  animateNumber('kpi-total',   kpi.total_facture,  v => formatMoney(v));
  animateNumber('kpi-nb',      kpi.nb_factures,    v => Math.round(v).toString());
  animateNumber('kpi-panier',  kpi.panier_moyen,   v => formatMoney(v));

  const topEl = document.getElementById('kpi-toparticle');
  topEl.textContent = kpi.top_article || '—';
  const occEl = document.getElementById('kpi-toparticle-occ');
  occEl.textContent = kpi.top_article ? `${kpi.top_article_occurrences}× occurrence${kpi.top_article_occurrences > 1 ? 's' : ''}` : '';

  // Anomalies count
  const anomCount = (data.anomalies || []).filter(a => !a.toLowerCase().includes('aucune')).length;
  document.getElementById('kpi-anomalies').textContent = anomCount || '0';

  // Badge évolution N-1
  const badgeEl = document.getElementById('kpi-evo-badge');
  badgeEl.innerHTML = '';
  if (data.comparaison_n1?.evolution_pct !== null && data.comparaison_n1?.evolution_pct !== undefined) {
    const pct = data.comparaison_n1.evolution_pct;
    const cls = pct > 5 ? 'up' : pct < -5 ? 'down' : 'neutral';
    const arrow = pct >= 0 ? '↑' : '↓';
    badgeEl.innerHTML = `<div class="kpi-badge ${cls}">${arrow} ${Math.abs(pct)}% vs N-1</div>`;
  }
}

// ─── Chart mensuel ───────────────────────────────────────────────────────────
function renderChartMensuel(data) {
  const canvas = document.getElementById('chart-mensuel');
  if (!canvas) return;
  if (chartMensuel) chartMensuel.destroy();

  const labels = ['Jan','Fév','Mar','Avr','Mai','Juin','Juil','Août','Sep','Oct','Nov','Déc'];
  const anCourant = data.plage.debut.slice(0, 4);

  const datasets = [{
    label: anCourant,
    data: data.totaux_mensuels,
    borderColor: '#3de8f4',
    backgroundColor: chartType === 'bar' ? 'rgba(61,232,244,0.25)' : 'rgba(61,232,244,0.08)',
    pointBackgroundColor: '#3de8f4',
    pointRadius: 4,
    pointHoverRadius: 7,
    fill: chartType === 'line',
    tension: 0.4,
    borderWidth: 2,
  }];

  if (data.comparaison_n1 && data.comparaison_n1.totaux_mensuels) {
    datasets.push({
      label: String(parseInt(anCourant) - 1),
      data: data.comparaison_n1.totaux_mensuels,
      borderColor: 'rgba(142,163,195,0.4)',
      backgroundColor: 'rgba(142,163,195,0.05)',
      pointBackgroundColor: 'rgba(142,163,195,0.4)',
      pointRadius: 3,
      fill: false,
      tension: 0.4,
      borderDash: [6, 4],
      borderWidth: 1.5,
    });
  }

  chartMensuel = new Chart(canvas.getContext('2d'), {
    type: chartType,
    data: { labels, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: {
          display: true,
          labels: { color: '#8ea3c3', font: { family: 'JetBrains Mono', size: 11 }, boxWidth: 12 }
        },
        tooltip: {
          backgroundColor: '#1a2235',
          borderColor: 'rgba(61,232,244,0.25)',
          borderWidth: 1,
          titleColor: '#f0f4ff',
          bodyColor: '#8ea3c3',
          titleFont: { family: 'Syne', size: 13 },
          bodyFont: { family: 'JetBrains Mono', size: 11 },
          callbacks: {
            label: ctx => ` ${ctx.dataset.label} : ${formatMoney(ctx.raw)}`
          }
        }
      },
      scales: {
        x: {
          grid: { color: 'rgba(255,255,255,0.04)' },
          ticks: { color: '#4d6080', font: { family: 'JetBrains Mono', size: 10 } }
        },
        y: {
          beginAtZero: true,
          grid: { color: 'rgba(255,255,255,0.04)' },
          ticks: {
            color: '#4d6080',
            font: { family: 'JetBrains Mono', size: 10 },
            callback: v => formatMoneyShort(v)
          }
        }
      }
    }
  });
}

// ─── Chart Donut ─────────────────────────────────────────────────────────────
function renderChartDonut(data) {
  const canvas = document.getElementById('chart-donut');
  if (!canvas) return;
  if (chartDonut) chartDonut.destroy();

  const rep = data.repartition_articles || [];
  if (!rep.length) { canvas.style.display = 'none'; return; }
  canvas.style.display = 'block';

  chartDonut = new Chart(canvas.getContext('2d'), {
    type: 'doughnut',
    data: {
      labels: rep.map(r => r.article),
      datasets: [{
        data: rep.map(r => r.montant),
        backgroundColor: PALETTE,
        borderColor: '#0b0f1a',
        borderWidth: 3,
        hoverOffset: 6,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: '68%',
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: '#1a2235',
          borderColor: 'rgba(61,232,244,0.25)',
          borderWidth: 1,
          titleColor: '#f0f4ff',
          bodyColor: '#8ea3c3',
          bodyFont: { family: 'JetBrains Mono', size: 11 },
          callbacks: {
            label: ctx => ` ${formatMoney(ctx.raw)} (${((ctx.raw / rep.reduce((a,b)=>a+b.montant,0))*100).toFixed(1)}%)`
          }
        }
      }
    }
  });

  // Légende custom
  const legendEl = document.getElementById('donut-legend');
  if (legendEl) {
    legendEl.innerHTML = rep.map((r, i) => `
      <div style="display:flex; align-items:center; gap:8px; font-size:11px; color:var(--text-secondary);">
        <div style="width:8px;height:8px;border-radius:50%;background:${PALETTE[i] || '#888'};flex-shrink:0;"></div>
        <span style="flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${r.article}</span>
        <span style="font-family:var(--font-mono); color:var(--text-primary);">${formatMoney(r.montant)}</span>
      </div>
    `).join('');
  }
}

// ─── Chart Trimestre ─────────────────────────────────────────────────────────
function renderChartTrimestre(data) {
  const canvas = document.getElementById('chart-trimestre');
  if (!canvas) return;
  if (chartTrimestre) chartTrimestre.destroy();

  const tm = data.totaux_mensuels || Array(12).fill(0);
  const trimesters = [
    tm[0]+tm[1]+tm[2],
    tm[3]+tm[4]+tm[5],
    tm[6]+tm[7]+tm[8],
    tm[9]+tm[10]+tm[11],
  ];

  chartTrimestre = new Chart(canvas.getContext('2d'), {
    type: 'bar',
    data: {
      labels: ['T1','T2','T3','T4'],
      datasets: [{
        label: 'Dépenses',
        data: trimesters,
        backgroundColor: ['rgba(61,232,244,0.6)','rgba(91,138,247,0.6)','rgba(244,114,182,0.6)','rgba(52,211,153,0.6)'],
        borderColor:      ['#3de8f4','#5b8af7','#f472b6','#34d399'],
        borderWidth: 2,
        borderRadius: 6,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: '#1a2235',
          borderColor: 'rgba(61,232,244,0.25)',
          borderWidth: 1,
          titleColor: '#f0f4ff',
          bodyColor: '#8ea3c3',
          bodyFont: { family: 'JetBrains Mono', size: 11 },
          callbacks: { label: ctx => ` ${formatMoney(ctx.raw)}` }
        }
      },
      scales: {
        x: { grid: { color: 'rgba(255,255,255,0.04)' }, ticks: { color: '#4d6080', font: { family: 'JetBrains Mono', size: 11 } } },
        y: { beginAtZero: true, grid: { color: 'rgba(255,255,255,0.04)' }, ticks: { color: '#4d6080', font: { family: 'JetBrains Mono', size: 10 }, callback: v => formatMoneyShort(v) } }
      }
    }
  });
}

// ─── Top Articles list ────────────────────────────────────────────────────────
function renderTopArticlesList(data) {
  const el = document.getElementById('top-articles-list');
  if (!el) return;

  const rep = data.repartition_articles || [];
  if (!rep.length) {
    el.innerHTML = '<div class="no-data"><div class="nd-icon">📭</div>Aucune donnée</div>';
    return;
  }

  const maxMontant = Math.max(...rep.map(r => r.montant), 1);
  el.innerHTML = rep.map((r, i) => {
    const pct = ((r.montant / maxMontant) * 100).toFixed(0);
    return `
      <div class="mini-stat-row">
        <div style="display:flex; align-items:center; gap:8px; flex:1; min-width:0;">
          <div style="width:8px;height:8px;border-radius:50%;background:${PALETTE[i]||'#888'};flex-shrink:0;"></div>
          <div class="mini-stat-label" style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${r.article}</div>
        </div>
        <div class="mini-stat-bar-wrap">
          <div class="mini-stat-bar" style="width:${pct}%; background:${PALETTE[i]||'var(--accent)'};"></div>
        </div>
        <div class="mini-stat-val">${formatMoney(r.montant)}</div>
      </div>
    `;
  }).join('');
}

// ─── Articles Table ───────────────────────────────────────────────────────────
function renderArticlesTable(data) {
  if (tableInstance) { try { tableInstance.destroy(); } catch(e){} tableInstance = null; }

  const articles = data.articles_comparaison || [];
  document.getElementById('articles-count-label').textContent = `${articles.length} article${articles.length > 1 ? 's' : ''}`;
  document.getElementById('table-displayed').textContent = articles.length;

  if (!articles.length) {
    document.getElementById('articles-table').innerHTML =
      '<div class="no-data"><div class="nd-icon">📭</div>Aucun article trouvé pour cette période.</div>';
    return;
  }

  // Calcul max prix_moyen pour les barres
  const maxPrix = Math.max(...articles.filter(a => a.prix_moyen).map(a => a.prix_moyen), 1);

  tableInstance = new Tabulator('#articles-table', {
    data: articles,
    layout: 'fitColumns',
    height: '420px',
    pagination: true,
    paginationSize: 12,
    headerSort: true,
    rowFormatter: (row) => {
      row.getElement().style.cssText = 'background:transparent; border-bottom:1px solid rgba(255,255,255,0.04);';
    },
    columns: [
      {
        title: 'Article',
        field: 'article',
        sorter: 'string',
        minWidth: 200,
        formatter: cell => {
          const val = cell.getValue() || '—';
          return `<span style="color:var(--text-primary); font-weight:500;">${val}</span>`;
        }
      },
      {
        title: 'Occ.',
        field: 'occurrences',
        sorter: 'number',
        width: 70,
        formatter: cell => {
          const v = cell.getValue();
          return `<span style="font-family:var(--font-mono); color:var(--accent); font-size:12px;">${v}</span>`;
        }
      },
      {
        title: 'Prix moyen',
        field: 'prix_moyen',
        sorter: 'number',
        width: 160,
        formatter: cell => {
          const v = cell.getValue();
          if (v === null || v === undefined) return '<span style="color:var(--text-muted);">—</span>';
          const pct = Math.min((v / maxPrix) * 100, 100);
          return `
            <div class="price-bar-cell">
              <span style="font-family:var(--font-mono); font-size:12px; color:var(--text-primary); min-width:70px;">${formatMoney(v)}</span>
              <div class="price-bar-inline"><div class="price-bar-fill" style="width:${pct}%;"></div></div>
            </div>`;
        }
      },
      {
        title: 'Min',
        field: 'prix_min',
        sorter: 'number',
        width: 110,
        formatter: cell => {
          const v = cell.getValue();
          return v !== null && v !== undefined
            ? `<span style="font-family:var(--font-mono); font-size:12px; color:var(--accent-ok);">${formatMoney(v)}</span>`
            : '<span style="color:var(--text-muted);">—</span>';
        }
      },
      {
        title: 'Max',
        field: 'prix_max',
        sorter: 'number',
        width: 110,
        formatter: cell => {
          const v = cell.getValue();
          return v !== null && v !== undefined
            ? `<span style="font-family:var(--font-mono); font-size:12px; color:var(--accent-3);">${formatMoney(v)}</span>`
            : '<span style="color:var(--text-muted);">—</span>';
        }
      },
      {
        title: 'Variation',
        field: 'prix_min',
        sorter: false,
        width: 110,
        formatter: cell => {
          const row  = cell.getRow().getData();
          const pMin = row.prix_min;
          const pMax = row.prix_max;
          if (!pMin || !pMax || pMin <= 0) return '<span class="var-badge var-low">—</span>';
          const varPct = ((pMax - pMin) / pMin * 100).toFixed(1);
          let cls = 'var-low', icon = '✓';
          if (varPct > 50)       { cls = 'var-high'; icon = '⚠'; }
          else if (varPct > 20)  { cls = 'var-mid';  icon = '△'; }
          return `<span class="var-badge ${cls}">${icon} ${varPct}%</span>`;
        }
      },
    ],
    dataFiltered: (filters, rows) => {
      const countEl = document.getElementById('table-displayed');
      if (countEl) countEl.textContent = rows.length;
    }
  });
}

// ─── Anomalies ────────────────────────────────────────────────────────────────
function renderAnomalies(data) {
  const list = document.getElementById('anomalies-list');
  if (!list) return;

  const anomalies = data.anomalies || [];
  const hasRealAnomalies = anomalies.some(a => !a.toLowerCase().includes('aucune anomalie'));

  if (!hasRealAnomalies) {
    list.innerHTML = `
      <div class="anomaly-item ok">
        <div class="anomaly-icon">✅</div>
        <div class="anomaly-text">Aucune anomalie détectée sur la période analysée.</div>
      </div>`;
    return;
  }

  list.innerHTML = anomalies
    .filter(a => !a.toLowerCase().includes('aucune anomalie'))
    .map(a => {
      let cls = 'warn', icon = '⚠️';
      if (a.toLowerCase().includes('variation') || a.toLowerCase().includes('prix')) {
        cls = 'danger'; icon = '🔺';
      }
      if (a.toLowerCase().includes('aucune facture')) {
        cls = 'warn'; icon = '📅';
      }
      // Mettre en gras les parties importantes
      const highlighted = a.replace(/'([^']+)'/g, '<strong>\'$1\'</strong>')
                           .replace(/(\d+[\s.,]\d+\s*€)/g, '<strong style="color:var(--accent);">$1</strong>');
      return `
        <div class="anomaly-item ${cls}">
          <div class="anomaly-icon">${icon}</div>
          <div class="anomaly-text">${highlighted}</div>
        </div>`;
    }).join('');
}

// ─── Heatmap articles × mois ─────────────────────────────────────────────────
function renderHeatmap(data) {
  const grid = document.getElementById('heatmap-grid');
  if (!grid) return;

  const moisLabels = ['J','F','M','A','M','J','J','A','S','O','N','D'];

  // Prendre les top 8 articles par occurrences
  const articles = (data.articles_comparaison || [])
    .sort((a, b) => b.occurrences - a.occurrences)
    .slice(0, 8);

  if (!articles.length) {
    grid.innerHTML = '<div class="no-data"><div class="nd-icon">🌡️</div>Pas assez de données pour la heatmap.</div>';
    return;
  }

  // Construire une matrice article × mois depuis repartition_articles
  // (On utilise totaux_mensuels pondérés par répartition)
  // Construction simplifiée : on utilise prix_moyen * occurrences / 12 comme proxy
  const tm = data.totaux_mensuels || Array(12).fill(0);
  const totalGeneral = tm.reduce((a, b) => a + b, 0) || 1;

  // Pour chaque article, on distribue ses dépenses proportionnellement aux totaux mensuels
  const rep = data.repartition_articles || [];
  const repMap = {};
  rep.forEach(r => { repMap[r.article] = r.montant; });

  // Calculer valeur max pour normalisation
  let maxVal = 0;
  const matrix = articles.map(art => {
    const artTotal = repMap[art.article] || (art.prix_moyen * art.occurrences) || 0;
    return tm.map(mTotal => {
      const v = artTotal * (mTotal / totalGeneral);
      if (v > maxVal) maxVal = v;
      return v;
    });
  });

  // Rendu HTML
  const cols = `auto repeat(12, 1fr)`;
  grid.style.cssText = `display:grid; grid-template-columns:${cols}; gap:4px; align-items:center;`;

  // Header mois
  grid.innerHTML = `<div></div>` + moisLabels.map(m => `<div class="hm-header">${m}</div>`).join('');

  // Rows
  articles.forEach((art, i) => {
    const shortName = art.article.length > 18 ? art.article.slice(0, 16) + '…' : art.article;
    grid.innerHTML += `<div class="hm-label" title="${art.article}">${shortName}</div>`;
    matrix[i].forEach((val, mIdx) => {
      const intensity = maxVal > 0 ? val / maxVal : 0;
      const alpha = 0.05 + intensity * 0.85;
      const color = intensity > 0.7 ? `rgba(61,232,244,${alpha})`
                  : intensity > 0.4 ? `rgba(91,138,247,${alpha})`
                  : `rgba(91,138,247,${alpha * 0.6})`;
      const valLabel = val > 0 ? formatMoney(val) : '—';
      grid.innerHTML += `<div class="hm-cell" style="background:${color};" data-val="${valLabel}" title="${art.article} – ${moisLabels[mIdx]}: ${valLabel}"></div>`;
    });
  });

  // Légende
  const legendRow = document.createElement('div');
  legendRow.style.cssText = 'grid-column:1/-1; display:flex; align-items:center; gap:8px; margin-top:12px; font-family:var(--font-mono); font-size:10px; color:var(--text-muted);';
  legendRow.innerHTML = `
    <span>Faible</span>
    <div style="flex:1; height:6px; border-radius:3px; background:linear-gradient(90deg, rgba(91,138,247,0.1), rgba(61,232,244,0.9));"></div>
    <span>Élevé</span>
  `;
  grid.appendChild(legendRow);
}

// ─── Tabs navigation ─────────────────────────────────────────────────────────
function switchTab(tabId) {
  activeTab = tabId;
  document.querySelectorAll('.an-tab').forEach(t => {
    t.classList.toggle('active', t.dataset.tab === tabId);
  });
  document.querySelectorAll('#an-results > div[id^="tab-"]').forEach(panel => {
    panel.style.display = panel.id === `tab-${tabId}` ? 'block' : 'none';
  });

  // Re-render charts si on revient sur overview (Canvas peut être invisible)
  if (tabId === 'overview' && lastData) {
    setTimeout(() => {
      renderChartMensuel(lastData);
      renderChartDonut(lastData);
      renderChartTrimestre(lastData);
    }, 50);
  }
}

// ─── Export Excel ─────────────────────────────────────────────────────────────
async function exportExcel() {
  const idConcession = document.getElementById('analyse-concession').value;
  const annee        = document.getElementById('analyse-annee').value;
  const mois         = document.getElementById('analyse-mois').value;
  if (!idConcession) { showToast('Sélectionnez une concession', 'warning'); return; }
  const params = new URLSearchParams({ id_concession: idConcession });
  if (annee) params.append('annee', annee);
  if (mois)  params.append('mois', mois);
  window.open(`/analyses/export-excel?${params.toString()}`, '_blank');
}

// ─── Helpers ──────────────────────────────────────────────────────────────────
function formatMoney(v) {
  if (v === null || v === undefined) return '—';
  return new Intl.NumberFormat('fr-FR', { style: 'currency', currency: 'EUR', minimumFractionDigits: 2 }).format(v);
}

function formatMoneyShort(v) {
  if (v === null || v === undefined) return '—';
  if (Math.abs(v) >= 1_000_000) return (v / 1_000_000).toFixed(1) + 'M€';
  if (Math.abs(v) >= 1_000)     return (v / 1_000).toFixed(0) + 'k€';
  return v + '€';
}

function animateNumber(elId, target, formatter) {
  const el = document.getElementById(elId);
  if (!el) return;
  const start   = 0;
  const duration = 900;
  const startTs  = performance.now();

  function step(ts) {
    const progress = Math.min((ts - startTs) / duration, 1);
    const ease     = 1 - Math.pow(1 - progress, 3); // ease-out cubic
    el.textContent = formatter(start + (target - start) * ease);
    if (progress < 1) requestAnimationFrame(step);
  }
  requestAnimationFrame(step);
}
