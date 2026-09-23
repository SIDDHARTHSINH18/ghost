import apiService from './apiService';

/**
 * Service for handling memory operations
 */
const memoryService = {
  /**
   * Fetch all memories
   * @returns {Promise<Array>} - List of memories
   */
  fetchMemories: async () => {
    const response = await apiService.get('/api/memory');
    return response || [];
  },

  /**
   * Create a new memory
   * @param {Object} memoryData - Memory data to create
   * @returns {Promise<Object>} - Created memory
   */
  createMemory: async (memoryData) => {
    const response = await apiService.post('/api/memory', memoryData);
    return response;
  },

  /**
   * Update a memory
   * @param {string} memoryId - ID of memory to update
   * @param {Object} memoryData - Updated memory data
   * @returns {Promise<Object>} - Updated memory
   */
  updateMemory: async (memoryId, memoryData) => {
    const response = await apiService.put(`/api/memory/${memoryId}`, memoryData);
    return response;
  },

  /**
   * Delete a memory
   * @param {string} memoryId - ID of memory to delete
   * @returns {Promise<Object>} - Delete response
   */
  deleteMemory: async (memoryId) => {
    const response = await apiService.delete(`/api/memory/${memoryId}`);
    return response;
  },

  /**
   * Delete all memories
   * @returns {Promise<Object>} - Response
   */
  deleteAllMemories: async () => {
    const response = await apiService.delete('/api/memory');
    return response;
  },

  /**
   * Search memories
   * @param {string} query - Search query
   * @returns {Promise<Array>} - Search results
   */
  searchMemories: async (query) => {
    const response = await apiService.get(`/api/memory/search?q=${encodeURIComponent(query)}`);
    return response || [];
  },

  /**
   * Get memory stats
   * @returns {Promise<Object>} - Memory statistics
   */
  getMemoryStats: async () => {
    const response = await apiService.get('/api/memory/stats');
    return response;
  },
};

export default memoryService;