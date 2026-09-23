import apiService from './apiService';
import { AUTH_TOKEN_KEY } from '../utils/constants';

/**
 * Clear the legacy sessionStorage copy of the token so
 * only one token store (localStorage) remains.
 */
function clearLegacyTokenStorage() {
  try {
    sessionStorage.removeItem(AUTH_TOKEN_KEY);
  } catch {
    // Best effort.
  }
}

/**
 * Authentication service for handling login, logout, and token management
 */
const authService = {
  /**
   * Check if user is authenticated
   * @returns {boolean} - True if authenticated
   */
  isAuthenticated: () => {
    const token = localStorage.getItem(AUTH_TOKEN_KEY);
    return !!token && token !== 'null' && token !== 'undefined';
  },

  /**
   * Get authentication token
   * @returns {string|null} - Auth token or null
   */
  getToken: () => {
    return localStorage.getItem(AUTH_TOKEN_KEY);
  },

  /**
   * Store authentication token as the single token source
   * @param {string} token - Auth token to store
   */
  setToken: (token) => {
    localStorage.setItem(AUTH_TOKEN_KEY, token);
    clearLegacyTokenStorage();
  },

  /**
   * Login user with credentials
   * @param {string} password - Password for authentication
   * @returns {Promise<Object>} - Login response
   */
  login: async (password) => {
    const response = await apiService.post('/api/auth/login', { password });
    
    if (response.token) {
      localStorage.setItem(AUTH_TOKEN_KEY, response.token);
      return response;
    }
    
    throw new Error('Login failed: No token received');
  },

  /**
   * Logout user and clear token
   */
  logout: () => {
    localStorage.removeItem(AUTH_TOKEN_KEY);
    clearLegacyTokenStorage();
    // Optionally call logout endpoint
    // apiService.post('/api/logout');
  },

  /**
   * Refresh authentication token
   * @returns {Promise<string>} - New token
   */
  refreshToken: async () => {
    const response = await apiService.post('/api/refresh-token');
    if (response.access_token) {
      localStorage.setItem(AUTH_TOKEN_KEY, response.access_token);
      return response.access_token;
    }
    throw new Error('Token refresh failed');
  },

  /**
   * Validate current token
   * @returns {Promise<boolean>} - True if token is valid
   */
  validateToken: async () => {
    if (!authService.isAuthenticated()) {
      return false;
    }
    
    try {
      await apiService.get('/api/auth/session');
      return true;
    } catch (error) {
      authService.logout();
      return false;
    }
  },
};

export default authService;