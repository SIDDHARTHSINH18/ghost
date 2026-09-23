import React from "react";

/**
 * StatusIndicator - Shows backend connection status
 * Displays a pulsing dot and label for connection state
 */
export default function StatusIndicator({ 
  status = "connected", 
  label = "ENMA ONLINE" 
}) {
  // Status to color mapping
  const getStatusColor = (status) => {
    switch (status) {
      case "connected":
      case "online":
        return "var(--color-state-completed)";
      case "connecting":
      case "pending":
        return "var(--color-state-listening)";
      case "disconnected":
      case "offline":
      case "error":
        return "var(--color-state-error)";
      default:
        return "var(--color-state-idle)";
    }
  };

  return (
    <div className="status-indicator status-indicator-theme" title={label}>
      <div
        className="status-dot"
        style={{
          backgroundColor: getStatusColor(status),
          boxShadow: 
            status === "connected" || status === "online"
              ? "0 0 12px var(--color-state-completed)"
              : "0 0 8px rgba(0,0,0,0.3)"
        }}
      />
      <span className="status-label">{label}</span>
    </div>
  );
}