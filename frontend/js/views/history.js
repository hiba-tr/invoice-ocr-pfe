import { showSpinner, hideSpinner, showToast } from '../app.js';
import { apiCall } from '../api.js';

export async function initHistoryView() {
  const container = document.getElementById('history-list');
  showSpinner();
  try {
    const factures = await apiCall('GET', '/factures');
    if (!factures.length) {
      container.innerHTML = '<div class="alert alert-info">Aucune facture enregistrée</div>';
      return;
    }

    const detailsPromises = factures.map(f => apiCall('GET', `/facture/${f.id_facture}/details`));
    const allDetails = await Promise.all(detailsPromises);

    let html = '<div class="accordion" id="historyAccordion">';
    for (let i = 0; i < factures.length; i++) {
      const f = factures[i];
      const details = allDetails[i];
      let dateAffichee = f.date_facture || 'N/A';
      if (dateAffichee.includes('T')) dateAffichee = dateAffichee.split('T')[0];
      const collapseId = `collapse${f.id_facture}`;
      const headingId = `heading${f.id_facture}`;

      html += `<div class="accordion-item border-0 mb-3 shadow-sm" style="border-radius: 16px; overflow: hidden;">
        <h2 class="accordion-header" id="${headingId}">
          <button class="accordion-button collapsed bg-white fw-semibold" type="button" data-bs-toggle="collapse" data-bs-target="#${collapseId}" aria-expanded="false" aria-controls="${collapseId}" style="border-radius: 16px !important; box-shadow: none;">
            <i class="fas fa-file-invoice me-3" style="color: var(--primary);"></i>
            <span>Facture #${f.id_facture} – ${dateAffichee}</span>
            <span class="badge bg-light text-dark ms-3">${details.details?.length || 0} ligne(s)</span>
          </button>
        </h2>
        <div id="${collapseId}" class="accordion-collapse collapse" aria-labelledby="${headingId}" data-bs-parent="#historyAccordion">
          <div class="accordion-body bg-light">
            <div class="d-flex justify-content-end mb-3">
              <button class="btn btn-sm btn-outline-secondary me-2 resume-btn" data-id="${f.id_facture}"><i class="fas fa-robot me-1"></i>Résumé IA</button>
              <button class="btn btn-sm btn-outline-danger delete-btn" data-id="${f.id_facture}"><i class="fas fa-trash me-1"></i>Supprimer</button>
            </div>`;

      if (details.details && details.details.length > 0) {
        const piv = {};
        details.details.forEach(d => {
          if (!piv[d.item]) piv[d.item] = {};
          piv[d.item][d.colonne] = d.valeur;
        });
        const colonnes = [...new Set(details.details.map(d => d.colonne))];
        html += `<div class="table-responsive"><table class="table table-sm table-hover align-middle bg-white" style="border-radius: 12px; overflow: hidden;">
          <thead class="table-light"><tr><th>Article</th>${colonnes.map(c => `<th>${c}</th>`).join('')}</tr></thead><tbody>`;
        Object.entries(piv).forEach(([item, vals]) => {
          html += `<tr><td class="fw-medium">${item}</td>${colonnes.map(c => `<td>${vals[c] || '∅'}</td>`).join('')}</tr>`;
        });
        html += `</tbody></table></div>`;
      } else {
        html += `<p class="text-muted fst-italic">Aucune ligne enregistrée pour cette facture.</p>`;
      }

      if (f.total_montant !== null && f.total_montant !== undefined) {
        html += `<div class="mt-3 text-end fw-bold">Total facture : ${parseFloat(f.total_montant).toFixed(2)} ${f.devise || '€'}</div>`;
      } else {
        html += `<div class="mt-3 text-end fw-bold text-muted">Total facture non renseigné</div>`;
      }
      html += `</div></div></div>`;
    }
    html += '</div>';
    container.innerHTML = html;

    document.querySelectorAll('.resume-btn').forEach(b => {
      b.addEventListener('click', async (e) => {
        e.stopPropagation();
        const id = e.currentTarget.dataset.id;
        showSpinner();
        try {
          const res = await apiCall('POST', `/facture/${id}/resume`);
          alert(res.resume?.resume_texte || 'Aucun résumé disponible.');
        } catch (e) { showToast('Erreur résumé', 'danger'); }
        finally { hideSpinner(); }
      });
    });

    document.querySelectorAll('.delete-btn').forEach(b => {
      b.addEventListener('click', async (e) => {
        e.stopPropagation();
        if (!confirm('Supprimer définitivement cette facture ?')) return;
        const id = e.currentTarget.dataset.id;
        showSpinner();
        try {
          await apiCall('DELETE', `/facture/${id}`);
          showToast('Facture supprimée', 'success');
          initHistoryView();
        } catch (e) { showToast('Erreur suppression', 'danger'); }
        finally { hideSpinner(); }
      });
    });

  } catch (error) {
    container.innerHTML = '<div class="alert alert-danger">Erreur lors du chargement de l\'historique.</div>';
  } finally {
    hideSpinner();
  }
}