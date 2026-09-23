import { API_URL, AUTH_TOKEN_KEY } from '../utils/constants';

/**
 * Centralized API service for making authenticated requests to the GHOST backend
 */
const apiService = {
  /**
   * Makes an authenticated fetch request
   * @param {string} endpoint - API endpoint (without base URL)
   * @param {Object} options - Fetch options
   * @returns {Promise<Response>} - Fetch response
   */
  authFetch: async (endpoint, options = {}) => {
    const token = localStorage.getItem(AUTH_TOKEN_KEY);
    const headers = {
      'Content-Type': 'application/json',
      ...options.headers,
    };

    if (token) {
      headers.Authorization = `Bearer ${token}`;
    }

    const response = await fetch(`${API_URL}${endpoint}`, {
      ...options,
      headers,
    });

    // Handle 401 Unauthorized - token might be expired
    if (response.status === 401) {
      // Clear invalid token
      localStorage.removeItem(AUTH_TOKEN_KEY);
      // Optionally redirect to login or trigger auth refresh
      window.dispatchEvent(new Event('authExpired'));
    }

    return response;
  },

  /**
   * GET request helper
   * @param {string} endpoint - API endpoint
   * @param {Object} params - Query parameters
   * @returns {Promise<any>} - Parsed JSON response
   */
  get: async (endpoint, params = {}) => {
    const queryString = new URLSearchParams(params).toString();
    const url = queryString ? `${endpoint}?${queryString}` : endpoint;
    const response = await apiService.authFetch(url);
    
    if (!response.ok) {
      throw new Error(`API request failed: ${response.status}`);
    }
    
    return response.json();
  },

  /**
   * POST request helper
   * @param {string} endpoint - API endpoint
   * @param {Object} data - Request body data
   * @returns {Promise<any>} - Parsed JSON response
   */
  post: async (endpoint, data = {}) => {
    const response = await apiService.authFetch(endpoint, {
      method: 'POST',
      body: JSON.stringify(data),
    });
    
    if (!response.ok) {
      throw new Error(`API request failed: ${response.status}`);
    }
    
    return response.json();
  },

  /**
   * PUT request helper
   * @param {string} endpoint - API endpoint
   * @param {Object} data - Request body data
   * @returns {Promise<any>} - Parsed JSON response
   */
  put: async (endpoint, data = {}) => {
    const response = await apiService.authFetch(endpoint, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
    
    if (!response.ok) {
      throw new Error(`API request failed: ${response.status}`);
    }
    
    return response.json();
  },

  /**
   * DELETE request helper
   * @param {string} endpoint - API endpoint
   * @returns {Promise<any>} - Parsed JSON response
   */
  delete: async (endpoint) => {
    const response = await apiService.authFetch(endpoint, {
      method: 'DELETE',
    });
    
    if (!response.ok) {
      throw new Error(`API request failed: ${response.status}`);
    }
    
    return response.json();
  },

  /**
   * Upload file using FormData
   * @param {FormData} formData - FormData object with file
   * @returns {Promise<any>} - Parsed JSON response
   */
  upload: async (formData) => {
    const token = localStorage.getItem(AUTH_TOKEN_KEY);
    const headers = {};
    
    if (token) {
      headers.Authorization = `Bearer ${token}`;
    }

    const response = await fetch(`${API_URL}/api/upload`, {
      method: 'POST',
      headers,
      body: formData,
    });

    if (!response.ok) {
      throw new Error(`Upload failed: ${response.status}`);
    }
    
    return response.json();
  },
};

export default apiService;