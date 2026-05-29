const API_BASE = '/api';

async function apiFetch(path, options = {}) {
  const url = new URL(path, window.location.origin);

  if (options.params) {
    for (const [key, value] of Object.entries(options.params)) {
      if (value !== undefined && value !== null && value !== '') {
        url.searchParams.append(key, value);
      }
    }
  }

  const response = await fetch(url.toString(), {
    method: options.method || 'GET',
    headers: { 'Content-Type': 'application/json' },
    body: options.body ? JSON.stringify(options.body) : undefined,
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.error || `Request failed (${response.status})`);
  }

  return response.json();
}

export const api = {
  getHealth: () => apiFetch(`${API_BASE}/health`),
  getAuthStatus: () => apiFetch(`${API_BASE}/auth/status`),
  refreshAuth: () => apiFetch(`${API_BASE}/auth/refresh`, { method: 'POST' }),

  getCatalogue: (params) => apiFetch(`${API_BASE}/catalogue`, { params }),
  getCurveData: (params) => apiFetch(`${API_BASE}/curve-data`, { params }),
  getFlows: (params) => apiFetch(`${API_BASE}/flows`, { params }),
  getAssessments: (params) => apiFetch(`${API_BASE}/assessments`, { params }),
  getFreight: (params) => apiFetch(`${API_BASE}/freight`, { params }),

  submitBulkDownload: (params) =>
    apiFetch(`${API_BASE}/bulk-download/job-submit`, { method: 'POST', params }),
  getBulkDownloadStatus: (jobId) =>
    apiFetch(`${API_BASE}/bulk-download/job-status/${jobId}`),
};
