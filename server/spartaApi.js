const fetch = require('node-fetch');

const SPARTA_API_BASE = process.env.SPARTA_API_BASE || 'https://api.sparta.app/v2';
const SPARTA_EMAIL = process.env.SPARTA_EMAIL;
const SPARTA_PASSWORD = process.env.SPARTA_PASSWORD;

let cachedToken = null;
let tokenExpiry = null;

async function authenticate() {
  const response = await fetch(`${SPARTA_API_BASE}/authenticate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: SPARTA_EMAIL, password: SPARTA_PASSWORD }),
  });

  const data = await response.json();

  if (!response.ok) {
    const error = new Error(data.message || 'Authentication failed');
    error.status = response.status;
    throw error;
  }

  cachedToken = data.token;
  // Token typically expires in 24h; we refresh 10 minutes early
  tokenExpiry = Date.now() + (data.expiresIn ? data.expiresIn * 1000 : 23 * 60 * 60 * 1000);

  console.log('Sparta API authenticated successfully');
  return cachedToken;
}

async function getToken() {
  if (cachedToken && tokenExpiry && Date.now() < tokenExpiry) {
    return cachedToken;
  }
  return authenticate();
}

function clearToken() {
  cachedToken = null;
  tokenExpiry = null;
}

async function request(path, queryParams = {}, method = 'GET', body = null) {
  const token = await getToken();

  const url = new URL(`${SPARTA_API_BASE}${path}`);
  for (const [key, value] of Object.entries(queryParams)) {
    if (value !== undefined && value !== null && value !== '') {
      url.searchParams.append(key, value);
    }
  }

  const options = {
    method,
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
  };

  if (body && method !== 'GET') {
    options.body = JSON.stringify(body);
  }

  const response = await fetch(url.toString(), options);

  // If unauthorized, try to re-authenticate once
  if (response.status === 401 || response.status === 403) {
    clearToken();
    const newToken = await getToken();
    options.headers['Authorization'] = `Bearer ${newToken}`;
    const retryResponse = await fetch(url.toString(), options);

    if (!retryResponse.ok) {
      const errorData = await retryResponse.json().catch(() => ({}));
      const error = new Error(errorData.message || `API request failed with status ${retryResponse.status}`);
      error.status = retryResponse.status;
      throw error;
    }

    return retryResponse.json();
  }

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    const error = new Error(errorData.message || `API request failed with status ${response.status}`);
    error.status = response.status;
    throw error;
  }

  return response.json();
}

module.exports = { getToken, clearToken, request };
