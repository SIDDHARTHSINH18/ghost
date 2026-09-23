import apiService from './apiService';

/**
 * Service for handling document operations
 */
const documentService = {
  /**
   * Fetch all documents
   * @returns {Promise<Array>} - List of documents
   */
  fetchDocuments: async () => {
    const response = await apiService.get('/api/documents');
    return response || [];
  },

  /**
   * Upload a document
   * @param {File} file - File to upload
   * @returns {Promise<Object>} - Upload response with document_id
   */
  uploadDocument: async (file) => {
    const formData = new FormData();
    formData.append('file', file);
    return await apiService.upload(formData);
  },

  /**
   * Delete a document
   * @param {string} documentId - ID of document to delete
   * @returns {Promise<Object>} - Delete response
   */
  deleteDocument: async (documentId) => {
    const response = await apiService.delete(`/api/documents/${documentId}`);
    return response;
  },

  /**
   * Set active document
   * @param {string} documentId - ID of document to set as active
   * @returns {Promise<Object>} - Response
   */
  setActiveDocument: async (documentId) => {
    const response = await apiService.post(`/api/documents/${documentId}/activate`);
    return response;
  },

  /**
   * Clear active document
   * @returns {Promise<Object>} - Response
   */
  clearActiveDocument: async () => {
    const response = await apiService.post('/api/documents/clear');
    return response;
  },

  /**
   * Fetch document content or metadata
   * @param {string} documentId - Document ID
   * @returns {Promise<Object>} - Document data
   */
  fetchDocument: async (documentId) => {
    const response = await apiService.get(`/api/documents/${documentId}`);
    return response;
  },

  /**
   * Search within documents
   * @param {string} query - Search query
   * @returns {Promise<Array>} - Search results
   */
  searchDocuments: async (query) => {
    const response = await apiService.get(`/api/documents/search?q=${encodeURIComponent(query)}`);
    return response || [];
  },
};

export default documentService;