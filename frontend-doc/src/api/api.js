import axios from 'axios';

export const API_BASE = 'http://localhost:8000';

export async function apiCall(method, url, data = null, params = null, queryParams = null) {
  const config = { 
    method, 
    url: API_BASE + url 
  };

  // Pour les paramètres query string (ex: ?force=true)
  if (queryParams) {
    config.params = queryParams;
  } else if (params) {
    config.params = params;
  }

  if (method === 'POST' || method === 'PUT' || method === 'PATCH') {
    if (data !== null) config.data = data;
  } else if (method === 'DELETE') {
    if (data !== null) config.data = data;
  }

  try {
    const response = await axios(config);
    return response.data;
  } catch (error) {
    if (error.response) {
      const apiError = new Error(error.response.data?.detail || error.message);
      apiError.status = error.response.status;
      throw apiError;
    }
    throw error;
  }
}