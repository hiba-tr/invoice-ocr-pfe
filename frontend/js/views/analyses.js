import { showSpinner, hideSpinner, showToast, state } from '../app.js';
import { apiCall } from '../api.js';

let chartMensuelInstance = null;

export async function initAnalysesView() {
  const selectConcession = document.getElementById('analyse-concession');
  const selectAnnee = document.getElementById('analyse-annee');

  showSpinner();
  try {
    const concessions = await apiCall('GET', '/concessions');
    selectConcession.innerHTML = '<option value="">-- Sélectionner une concession --</option>';
    concessions.forEach(c => selectConcession.innerHTML += `<option value="${c.id_concession}">${c.nom}</option>`);

    const currentYear = new Date().getFullYear();
    selectAnnee.innerHTML = '';
    for (let y = currentYear; y >= 2020; y--) {
      selectAnnee.innerHTML += `<option value="${y}">${y}</option>`;
    }
  } catch (e) {
    showToast('Erreur chargement concessions', 'danger');
  } finally {
    hideSpinner();
  }

  document.getElementById('lancer-analyse')?.addEventListener('click', async () => {
    const idConcession = selectConcession.value;
    const annee = selectAnnee.value;
    if (!idConcession || !annee) {
      showToast('Veuillez sélectionner une concession et une année', 'warning');
      return;
    }
    showSpinner();
    try {
      const data = await apiCall('GET', '/analyses/comparaison', null, { id_concession: idConcession, annee: parseInt(annee) });
      if (!data.nb_factures || data.nb_factures === 0) {
        document.getElementById('analyse-resultats').style.display = 'block';
        document.getElementById('analyse-titre').innerHTML = `<span class="concession-badge">${data.concession}</span> Année ${data.annee} · 0 facture`;
        document.getElementById('chart-mensuel').style.display = 'none';
        document.querySelector('#table-articles').parentElement.innerHTML = '<p class="text-muted mt-3">Aucune facture trouvée pour cette période.</p>';
        return;
      }
      afficherResultatsAnalyse(data);
    } catch (e) {
      showToast('Erreur analyse', 'danger');
    } finally {
      hideSpinner();
    }
  });
}

function afficherResultatsAnalyse(data) {
  document.getElementById('analyse-resultats').style.display = 'block';
  document.getElementById('analyse-titre').innerHTML = `<span class="concession-badge">${data.concession}</span> Année ${data.annee} · ${data.nb_factures} facture(s)`;

  const chartCanvas = document.getElementById('chart-mensuel');
  chartCanvas.style.display = 'block';
  const ctx = chartCanvas.getContext('2d');
  if (chartMensuelInstance) chartMensuelInstance.destroy();

  const hasData = data.totaux_mensuels && data.totaux_mensuels.some(v => v > 0);
  chartMensuelInstance = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: ['Jan', 'Fév', 'Mar', 'Avr', 'Mai', 'Juin', 'Juil', 'Août', 'Sep', 'Oct', 'Nov', 'Déc'],
      datasets: [{
        label: 'Total (€)',
        data: data.totaux_mensuels || Array(12).fill(0),
        backgroundColor: hasData ? 'rgba(79, 70, 229, 0.7)' : 'rgba(203, 213, 225, 0.5)',
        borderRadius: 8
      }]
    },
    options: {
      responsive: true,
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: (ctx) => hasData ? `${ctx.raw.toFixed(2)} €` : 'Aucun montant enregistré' } }
      },
      scales: {
        y: { beginAtZero: true, ticks: { callback: (val) => val + ' €' }, max: hasData ? undefined : 1 }
      }
    }
  });

  const oldAnnotation = chartCanvas.parentNode.querySelector('.annotation-text');
  if (oldAnnotation) oldAnnotation.remove();
  if (!hasData) {
    const annotation = document.createElement('div');
    annotation.className = 'text-muted small mt-2 text-center annotation-text';
    annotation.innerText = 'Aucun montant total n\'a été enregistré pour ces factures.';
    chartCanvas.parentNode.appendChild(annotation);
  }

  const tbody = document.querySelector('#table-articles tbody');
  tbody.innerHTML = '';
  if (!data.articles_comparaison || data.articles_comparaison.length === 0) {
    tbody.innerHTML = '<tr><td colspan="6" class="text-center text-muted">Aucun article avec prix unitaire trouvé</td></tr>';
    return;
  }

  data.articles_comparaison.sort((a,b) => (b.occurrences || 0) - (a.occurrences || 0));
  data.articles_comparaison.forEach(art => {
    const row = document.createElement('tr');
    const variation = art.prix_max && art.prix_min ? ((art.prix_max - art.prix_min) / art.prix_min * 100) : 0;
    row.innerHTML = `
      <td class="fw-medium">${art.article}</td>
      <td>${art.occurrences}</td>
      <td>${art.prix_moyen ? art.prix_moyen.toFixed(2) + ' €' : '—'}</td>
      <td>${art.prix_min ? art.prix_min.toFixed(2) + ' €' : '—'}</td>
      <td>${art.prix_max ? art.prix_max.toFixed(2) + ' €' : '—'}</td>
      <td>${art.prix_min && art.prix_max ? `<span class="badge ${variation > 20 ? 'bg-warning' : 'bg-success'}">${variation.toFixed(1)}%</span>` : '—'}</td>
    `;
    tbody.appendChild(row);
  });
}