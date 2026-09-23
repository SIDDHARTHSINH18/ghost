import apiService from './apiService';

/**
 * Service for graph data operations, backed by the
 * authenticated apiService layer (Phase 2 architecture).
 *
 * All endpoints mirror the real backend routes:
 * - GET  /api/graph        full knowledge graph (nodes + edges)
 * - GET  /api/tasks/{id}   one task with full metadata
 * - GET  /api/memory       memories (full content, dedicated endpoint)
 * - GET  /api/documents    document metadata
 * - GET  /api/tasks        task list (metadata only)
 */
const graphService = {
  /**
   * Fetch the GHOST knowledge graph
   * @returns {Promise<Object>} - { success, nodes, edges, stats }
   */
  fetchGraphData: async () => {
    return apiService.get('/api/graph');
  },

  /**
   * Fetch one task with full metadata (priority, result, error)
   * @param {string} taskId - Task UUID
   * @returns {Promise<Object>} - Task detail
   */
  fetchTaskDetail: async (taskId) => {
    return apiService.get(`/api/tasks/${taskId}`);
  },

  /**
   * Fetch all memories (full content via the dedicated memory API)
   * @returns {Promise<Object>} - { memories, total }
   */
  fetchMemories: async () => {
    return apiService.get('/api/memory');
  },

  /**
   * Fetch all documents (metadata only)
   * @returns {Promise<Object>} - { documents, total, total_size_bytes }
   */
  fetchDocuments: async () => {
    return apiService.get('/api/documents');
  },

  /**
   * Fetch all tasks (metadata only)
   * @returns {Promise<Object>} - { tasks, total }
   */
  fetchTasks: async () => {
    return apiService.get('/api/tasks');
  },
};

export default graphService;
