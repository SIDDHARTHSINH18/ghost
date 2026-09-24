import React from "react";
import { formatDateTime } from "../../utils/helpers";

/**
 * Message - Individual chat bubble component
 * Displays messages with proper styling for user vs assistant
 */
export default function Message({ 
  message, 
  isUser = false, 
  timestamp = null,
  sources = [],
  thinking = false 
}) {
  return (
    <div className={`message message-theme ${isUser ? "message-user" : "message-assistant"}`}>
      {/* Message Avatar */}
      {!isUser && !thinking && (
        <div className="message-avatar">
          <div className="avatar-ghost-core">
            <div className="avatar-disc" />
            <div className="avatar-orbit" />
          </div>
          <span className="avatar-label">E</span>
        </div>
      )}

      <div className="message-content">
        {/* Message Header */}
        <div className="message-header">
          {!isUser && (
            <div className="message-sender">
              <span className="sender-ghost">ENMA</span>
              <span className="sender-dot" />
            </div>
          )}
          {timestamp && (
            <div className="message-timestamp">
              {formatDateTime(timestamp)}
            </div>
          )}
        </div>

        {/* Message Text */}
        <div className="message-text">
          {thinking && (
            <div className="message-thinking">
              <div className="thinking-dots">
                <span /> <span /> <span />
              </div>
              <span className="thinking-text">ENMA is thinking...</span>
            </div>
          )}
          
          {!thinking && message && (
            <div className="message-body">
              {/* Simple markdown-like formatting */}
              {message
                .split('\n')
                .map((line, index) => {
                  // Handle code blocks
                  if (line.trim().startsWith('```')) {
                    return (
                      <div key={`code-block-${index}`} className="message-code-block">
                        {/* Code block content would go here - simplified for now */}
                        <code className="code-block-content">[code block]</code>
                        <button className="code-copy-btn" aria-label="Copy code">
                          <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="1.5">
                            <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
                            <path d="M5 15H4a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v2" />
                          </svg>
                        </button>
                      </div>
                    );
                  }
                  
                  // Handle regular lines
                  return (
                    <div key={`line-${index}`} className="message-line">
                      {line}
                    </div>
                  );
                })
              }
            </div>
          )}
        </div>

        {/* Sources / Citations */}
        {sources && sources.length > 0 && !isUser && (
          <div className="message-sources">
            <div className="sources-label">SOURCES:</div>
            <div className="sources-list">
              {sources.map((source, index) => (
                <span key={index} className="source-chip">
                  {source.document || source.source || `Source ${index + 1}`}
                  {source.pages && source.pages.length > 0 && (
                    <span className="source-pages">P.{source.pages.join(', ')}</span>
                  )}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}