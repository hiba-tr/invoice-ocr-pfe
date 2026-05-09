import axios from 'axios';

const API_BASE = 'http://localhost:8000';

export async function apiCall(method, url, data = null, params = null) {
  const response = await axios({ method, url: API_BASE + url, data, params });
  return response.data;
}

export { API_BASE };