// Shared UI components for the LM Studio Optimizer web UI.
// Every page reuses these instead of re-inventing markup inline.

// Escape every dynamic value before it enters template HTML. Model names,
// ids, errors and toast text are untrusted input.
const esc = (value) => String(value ?? '')
  .replace(/&/g, '&amp;')
  .replace(/</g, '&lt;')
  .replace(/>/g, '&gt;')
  .replace(/"/g, '&quot;')
  .replace(/'/g, '&#39;');

export const Components = {
  esc,
  card({ header, body, className = '' }) {
    return `
      <div class="card ${className}">
        ${header ? `<div class="card-header">${header}</div>` : ''}
        <div class="card-body">${body}</div>
      </div>`;
  },

  badge(kind = 'info', label) {
    const map = {
      success: 'badge-success',
      error: 'badge-error',
      warning: 'badge-warning',
      info: 'badge-info',
      gray: 'badge-gray',
    };
    return `<span class="badge ${map[kind] || map.info}">${esc(label)}</span>`;
  },

  statCard({ icon, value, label, hint, warn = false }) {
    return `
      <div class="card p-6 text-center" title="${esc(hint || '')}">
        <div class="text-4xl mb-2">${icon}</div>
        <div class="text-3xl font-bold ${warn ? 'text-red-600' : 'text-gray-900'}">${esc(value)}</div>
        <div class="text-sm text-gray-500">${esc(label)}</div>
        ${hint ? `<div class="text-xs text-gray-400 mt-1">${esc(hint)}</div>` : ''}
      </div>`;
  },

  emptyState({ icon, title, subtitle, action }) {
    return `
      <div class="empty-state">
        <svg class="empty-state-icon" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          ${icon || '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path>'}
        </svg>
        <h3 class="text-lg font-medium text-gray-900">${esc(title)}</h3>
        ${subtitle ? `<p class="text-gray-500 mt-1">${esc(subtitle)}</p>` : ''}
        ${action || ''}
      </div>`;
  },

  modalOverlay(id, title, body) {
    return `
      <div class="modal-overlay" id="${id}" role="dialog" aria-modal="true" aria-labelledby="${id}-title">
        <div class="modal-content" role="document">
          <div class="modal-header">
            <h3 class="text-lg font-semibold" id="${id}-title">${esc(title)}</h3>
            <button class="modal-x" aria-label="Close" onclick="document.getElementById('${id}').remove()">&times;</button>
          </div>
          <div class="modal-body">${body}</div>
        </div>
      </div>`;
  },

  toast(message, type = 'info') {
    return `
      <div class="toast toast-${type}" role="status" aria-live="polite">
        <div class="flex items-center gap-2 p-4 bg-white rounded-lg shadow-lg border-l-4">
          <span class="text-sm font-medium text-gray-900">${message}</span>
        </div>
      </div>`;
  },
};
