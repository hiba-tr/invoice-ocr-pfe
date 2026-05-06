import { showSpinner, hideSpinner, showToast } from '../app.js';
import { apiCall } from '../api.js';

export async function initDatabaseView() {
  showSpinner();
  try {
    // Items
    const itemsContainer = document.getElementById('items-table-container');
    const items = await apiCall('GET', '/items');
    let html = `<button class="btn btn-sm btn-danger mb-3" id="delete-selected-items"><i class="fas fa-trash"></i> Supprimer sélection</button>`;
    html += `<table class="table table-hover"><thead><tr><th><input type="checkbox" id="select-all-items"></th><th>ID</th><th>Libellé</th><th>Concession</th></tr></thead><tbody>`;
    items.forEach(it => { html += `<tr><td><input type="checkbox" class="item-checkbox" value="${it.id_item}"></td><td>${it.id_item}</td><td>${it.libelle_canonique}</td><td>${it.id_concession}</td></tr>`; });
    html += `</tbody></table>`;
    itemsContainer.innerHTML = html;

    document.getElementById('select-all-items')?.addEventListener('change', (e) => {
      document.querySelectorAll('.item-checkbox').forEach(cb => cb.checked = e.target.checked);
    });
    document.getElementById('delete-selected-items')?.addEventListener('click', async () => {
      const selected = [...document.querySelectorAll('.item-checkbox:checked')].map(cb => parseInt(cb.value));
      if (!selected.length) return;
      if (!confirm(`Supprimer ${selected.length} item(s) ?`)) return;
      showSpinner();
      try {
        await apiCall('DELETE', '/items', selected);
        showToast('Items supprimés');
        initDatabaseView();
      } catch (e) { showToast('Erreur suppression', 'danger'); }
      finally { hideSpinner(); }
    });

    // Colonnes
    const cols = await apiCall('GET', '/colonnes');
    document.getElementById('columns-table-container').innerHTML = `<table class="table"><thead><tr><th>ID</th><th>Libellé</th><th>Concession</th></tr></thead><tbody>${cols.map(c => `<tr><td>${c.id_colonne}</td><td>${c.libelle_canonique}</td><td>${c.id_concession}</td></tr>`).join('')}</tbody></table>`;

    // Factures
    const facts = await apiCall('GET', '/factures');
    document.getElementById('invoices-table-container').innerHTML = `<table class="table"><thead><tr><th>ID</th><th>Date</th><th>Concession</th><th>Fichier</th></tr></thead><tbody>${facts.map(f => `<tr><td>${f.id_facture}</td><td>${f.date_facture}</td><td>${f.id_concession}</td><td>${f.fichier_source}</td></tr>`).join('')}</tbody></table>`;

    // Concessions
    const concessions = await apiCall('GET', '/concessions');
    document.getElementById('concessions-table-container').innerHTML = `<table class="table"><thead><tr><th>ID</th><th>Nom</th><th>Création</th></tr></thead><tbody>${concessions.map(c => `<tr><td>${c.id_concession}</td><td>${c.nom}</td><td>${c.date_creation}</td></tr>`).join('')}</tbody></table>`;

  } catch (e) {
    showToast('Erreur chargement base de données', 'danger');
  } finally {
    hideSpinner();
  }
}