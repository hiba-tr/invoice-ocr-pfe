import { initUploadView } from './views/upload.js';
import { initHistoryView } from './views/history.js';
import { initDatabaseView } from './views/database.js';
import { initAnalysesView } from './views/analyses.js';
import { initManualView } from './views/manual.js';

// ---------- GLOBAL STATE ----------
export const state = {
  currentView: 'upload',
  uploadedFile: null,
  extractionResult: null,
  selectedInvoiceIndex: 0,
  editedTableData: [],
  tableColumns: [],
  concessionsList: [],
  currentConcessionId: null,
  currentConcessionNom: '',
  suggestions: [],
  tableInstance: null,
  firstColumnName: 'Description',
  totalGeneral: 0
};

// ---------- UTILS ----------
export function showSpinner() {
  document.getElementById('global-spinner').style.display = 'flex';
}
export function hideSpinner() {
  document.getElementById('global-spinner').style.display = 'none';
}

export function showToast(message, type = 'success') {
  const container = document.querySelector('.toast-container');
  const toastEl = document.createElement('div');
  toastEl.className = `toast align-items-center text-white bg-${type} border-0`;
  toastEl.setAttribute('role', 'alert');
  toastEl.innerHTML = `
    <div class="d-flex">
      <div class="toast-body">${message}</div>
      <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
    </div>`;
  container.appendChild(toastEl);
  const toast = new bootstrap.Toast(toastEl);
  toast.show();
  setTimeout(() => toastEl.remove(), 5000);
}

// ---------- TEMPLATES LOADING ----------
async function loadTemplates() {
  const views = ['upload', 'history', 'database', 'analyses', 'manual'];
  for (const view of views) {
    const response = await fetch(`templates/${view}.html`);
    if (!response.ok) {
      console.error(`Template ${view} not found`);
      continue;
    }
    const html = await response.text();
    const scriptEl = document.createElement('script');
    scriptEl.type = 'text/template';
    scriptEl.id = `template-${view}`;
    scriptEl.innerHTML = html;
    document.body.appendChild(scriptEl);
  }
}

// ---------- NAVIGATION ----------
function setActiveView(viewId) {
  state.currentView = viewId;
  document.querySelectorAll('#sidebar-nav .nav-link').forEach(link => {
    link.classList.remove('active');
    if (link.dataset.view === viewId) link.classList.add('active');
  });
  renderView(viewId);
}

function renderView(viewId) {
  const container = document.getElementById('view-container');
  const template = document.getElementById(`template-${viewId}`);
  if (!template) {
    container.innerHTML = '<div class="alert alert-danger">Template introuvable</div>';
    return;
  }
  container.innerHTML = template.innerHTML;

  if (viewId === 'upload') initUploadView();
  else if (viewId === 'history') initHistoryView();
  else if (viewId === 'database') initDatabaseView();
  else if (viewId === 'analyses') initAnalysesView();
  else if (viewId === 'manual') initManualView();
}

// ---------- INIT ----------
(async function() {
  await loadTemplates();
  document.querySelectorAll('#sidebar-nav .nav-link').forEach(link => {
    link.addEventListener('click', (e) => {
      e.preventDefault();
      setActiveView(link.dataset.view);
    });
  });
  setActiveView('upload');
})();