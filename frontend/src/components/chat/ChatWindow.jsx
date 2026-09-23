import React, { useEffect, useRef } from "react";

/**
 * ChatWindow - Scrollable message container
 * Displays a list of messages with auto-scroll functionality
 */
export default function ChatWindow({ messages }) {
  const messagesEndRef = useRef(null);

  // Scroll to bottom when new messages arrive
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  return (
    <div className="chat-window chat-window-theme">
      <div className="chat-messages">
        {messages.map((message, index) => (
          <div key={index} className="message-container">
            <Message 
              message={message.content || message.message || ""}
              isUser={message.role === "user" || message.isUser === true}
              timestamp={message.timestamp || message.createdAt}
              sources={message.sources || []}
              thinking={message.thinking === true || message.status === "thinking"}
            />
          </div>
        ))}
        
        {/* Scroll spacer */}
        <div ref={messagesEndRef} className="messages-end-spacer" />
      </div>
      
      {/* Typing Indicator (optional) */}
      <div className="chat-typing-indicator">
        <div className="typing-dots">
          <span /> <span /> <span />
        </div>
      </div>
    </div>
  );
}