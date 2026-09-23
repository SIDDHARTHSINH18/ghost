import React from "react";

/**
 * ChatHeader - Displays document context and chat mode indicators
 * Shows active document info and whether we're in task or chat mode
 */
export default function ChatHeader({ 
  activeDocument = null, 
  mode = "chat", 
  onDocumentChange 
}) {
  return (
    <div className="chat-header chat-header-theme">
      <div className="chat-header-content">
        {/* Mode Indicator */}
        <div className="chat-mode-indicator">
          <span className={`chat-mode-badge ${mode === "task" ? "task-mode" : "chat-mode"}`}>
            {mode === "task" ? "TASK MODE" : "CHAT MODE"}
          </span>
        </div>
        
        {/* Document Context */}
        {activeDocument && (
          <div className="chat-document-context">
            <div className="doc-icon">📄</div>
            <div className="doc-info">
              <p className="doc-title">{activeDocument.name || activeDocument.filename || "Untitled"}</p>
              <p className="doc-meta">
                {activeDocument.size ? 
                  `${activeDocument.size} bytes` : 
                  activeDocument.type ? 
                  `${activeDocument.type.toUpperCase()} DOC` : 
                  "DOCUMENT"
                }
              </p>
            </div>
            <button 
              className="doc-change-btn" 
              onClick={onDocumentChange} 
              aria-label="Change document"
            >
              <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.5">
                <circle cx="12" cy="12" r="10" />
                <line x1="12" y1="8" x2="12" y2="12" />
                <line x1="8" y1="12" x2="12" y2="12" />
              </svg>
            </button>
          </div>
        )}
        
        {/* Quick Actions */}
        <div className="chat-quick-actions">
          <button 
            className="quick-action-btn" 
            aria-label="New conversation"
          >
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M12 2v20M2 12h20" />
            </svg>
          </button>
          <button 
            className="quick-action-btn" 
            aria-label="Clear chat"
          >
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z" />
            </svg>
          </button>
        </div>
      </div>
    </div>
  );
}