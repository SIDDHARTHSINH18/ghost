import React, { useRef, useState } from "react";
import apiService from "../../services/apiService";

/**
 * Composer - Message input area with file attachment and send functionality
 * Updated to use theme variables and match the new design system
 */
export default function Composer({
  message,
  setMessage,
  sendMessage,
  loading,
  setDocumentId,
  documentId
}) {
  const fileInputRef = useRef(null);
  const [selectedFile, setSelectedFile] = useState(null);
  const [uploading, setUploading] = useState(false);

  const handleFileSelect = async (event) => {
    const file = event.target.files[0];

    if (!file) return;

    setSelectedFile(file);
    setUploading(true);

    const formData = new FormData();
    formData.append("file", file);

    try {
      const data = await apiService.upload(formData);

      setDocumentId(data.document_id);

      console.log("Document indexed:", data);

    } catch (error) {
      console.error(error);

      alert("File upload failed.");

      setSelectedFile(null);
      setDocumentId(null);

    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="composer composer-theme">
      <div className="composer-content">
        {/* File Preview */}
        {(selectedFile || documentId) && (
          <div className="composer-file-preview">
            <span className="file-icon">📎</span>
            <span className="file-info">
              {selectedFile ? selectedFile.name : "Document attached"}
              {uploading ? " • Processing..." : " • Ready"}
            </span>
            {!selectedFile && documentId && (
              <button 
                className="file-remove-btn" 
                onClick={() => setDocumentId(null)}
                aria-label="Remove document"
              >
                <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="1.5">
                  <line x1="18" y1="6" x2="6" y2="18" />
                  <line x1="6" y1="6" x2="18" y2="18" />
                </svg>
              </button>
            )}
          </div>
        )}

        <div className="composer-input-row">
          {/* Attach Button */}
          <button
            type="button"
            onClick={() => fileInputRef.current.click()}
            disabled={loading || uploading}
            className="composer-attach-btn"
            aria-label="Attach file"
          >
            <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 0-2.83 2.83l-8.49-8.48" />
            </svg>
          </button>

          {/* Hidden File Input */}
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.doc,.docx,.txt"
            onChange={handleFileSelect}
            className="composer-file-input"
          />

          {/* Text Input */}
          <input
            type="text"
            value={message}
            onChange={(event) =>
              setMessage(event.target.value)
            }
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                sendMessage();
              }
            }}
            placeholder="Ask ENMA anything..."
            disabled={loading}
            className="composer-input"
          />

          {/* Send Button */}
          <button
            onClick={sendMessage}
            disabled={loading || !message.trim()}
            className={`composer-send-btn ${loading || !message.trim() ? "disabled" : ""}`}
          >
            {loading ? (
              <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M12 6v6l4 2" />
              </svg>
            ) : (
              <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2">
                <line x1="22" y1="2" x2="11" y2="13" />
                <line x1="22" y1="2" x2="15.035" y2="10.965" />
                <line x1="2" y1="12" x2="22" y2="12" />
                <line x1="2" y1="12" x2="22" y2="12" />
              </svg>
            )}
          </button>
        </div>
        
        {/* Character Counter / Help Text */}
        <div className="composer-footer">
          <span className="composer-help">
            {message.length}/1000 characters
          </span>
          <span className="composer-shortcuts">
            Cmd+Enter to send • Shift+Enter for new line
          </span>
        </div>
      </div>
    </div>
  );
}