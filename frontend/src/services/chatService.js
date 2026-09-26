import apiService from './apiService';
import { CHAT_PROVIDER } from '../utils/constants';

/**
 * Service for handling chat and task messaging
 * Routes messages to appropriate endpoints based on content
 */
const chatService = {
  /**
   * Task signals that indicate a request should be treated as a task
   * Matches the logic in the original App.jsx
   */
  taskSignals: [
    "check whether",
    "check if",
    "find the file",
    "find a file",
    "create a file",
    "delete a file",
    "read the file",
    "list the files",
    "list files",
    "organize",
    "rename",
    "move the file",
    "copy the file",
    "send an email",
    "send a message",
    "open the application",
    "run the command",
    "execute",
  ],

  /**
   * Determine if a message looks like a task request
   * @param {string} message - User message
   * @returns {boolean} - True if message should be routed to task endpoint
   */
  looksLikeTask: (message) => {
    const lowerMessage = message.toLowerCase();
    return chatService.taskSignals.some((signal) =>
      lowerMessage.includes(signal),
    );
  },

  /**
   * Send a message to the appropriate endpoint
   * @param {string} message - User message
   * @param {Object} options - Additional options (documentId, history, etc.)
   * @returns {Promise<Object>} - Response from API
   */
  sendMessage: async (message, options = {}) => {
    const { documentId = null, history = [] } = options;
    
    if (chatService.looksLikeTask(message)) {
      // Route to task endpoint
      const response = await apiService.post('/api/tasks', {
        request: message,
      });
      return response;
    } else {
      // Route to chat endpoint
      const response = await apiService.post('/api/chat', {
        message,
        provider: CHAT_PROVIDER,
        model: null,
        document_id: documentId,
        history: history,
      });
      return response;
    }
  },

  /**
   * Send a streaming chat message
   * @param {string} message - User message
   * @param {Object} options - Additional options
   * @param {Function} onChunk - Callback for each chunk of response
   * @returns {Promise<void>}
   */
  sendStreamingMessage: async (message, options = {}, onChunk) => {
    const { documentId = null, history = [] } = options;
    
    // Check if it's a task - if so, we can't stream (tasks are synchronous)
    if (chatService.looksLikeTask(message)) {
      const response = await chatService.sendMessage(message, options);
      // Simulate streaming by sending the whole response as one chunk
      if (onChunk) {
        onChunk(JSON.stringify(response, null, 2));
      }
      return;
    }

    // For chat, we can attempt streaming if the backend supports it
    try {
      const response = await apiService.authFetch('/api/chat', {
        method: 'POST',
        body: JSON.stringify({
          message,
          provider: CHAT_PROVIDER,
          model: null,
          document_id: documentId,
          history: history,
          stream: true, // Request streaming
        }),
      });

      if (!response.ok) {
        throw new Error(`Chat request failed: ${response.status}`);
      }

      // Handle streaming response
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          let lines = buffer.split('\n');
          buffer = lines.pop(); // Keep incomplete line in buffer

          for (const line of lines) {
            if (line.startsWith('data: ')) {
              const data = line.slice(6);
              if (data === '[DONE]') {
                return;
              }
              try {
                const parsed = JSON.parse(data);
                if (onChunk) {
                  onChunk(parsed);
                }
              } catch (e) {
                // If not JSON, treat as text
                if (onChunk) {
                  onChunk(data);
                }
              }
            }
          }
        }
      } finally {
        reader.releaseLock();
      }
    } catch (error) {
      // Fallback to regular request if streaming fails
      const response = await chatService.sendMessage(message, options);
      if (onChunk) {
        onChunk(response);
      }
    }
  },
};

export default chatService;