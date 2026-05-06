const API_BASE = 'http://localhost:8000';

async function apiCall(method, url, data = null, params = null) {
  const response = await axios({ method, url: API_BASE + url, data, params });
  return response.data;
}

export { API_BASE, apiCall };