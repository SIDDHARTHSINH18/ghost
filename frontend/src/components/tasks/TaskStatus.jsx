import React from "react";

/**
 * TaskStatus - Visual status indicator for task execution
 * Shows colored dots and labels for different task states
 */
export default function TaskStatus({ status, size = "md" }) {
  // Status to color mapping
  const getStatusColor = (status) => {
    switch (status) {
      case "idle":
      case "pending":
        return "var(--color-state-idle)";
      case "listening":
      case "thinking":
        return "var(--color-state-listening)";
      case "planning":
        return "var(--color-state-planning)";
      case "executing":
        return "var(--color-state-executing)";
      case "verifying":
        return "var(--color-state-verifying)";
      case "completed":
        return "var(--color-state-completed)";
      case "error":
      case "failed":
        return "var(--color-state-error)";
      case "approval_required":
        return "var(--color-state-error)"; // Same as error for now
      default:
        return "var(--color-state-idle)";
    }
  };

  // Status to label mapping
  const getStatusLabel = (status) => {
    switch (status) {
      case "idle": return "IDLE";
      case "pending": return "PENDING";
      case "listening": return "LISTENING";
      case "thinking": return "THINKING";
      case "planning": return "PLANNING";
      case "executing": return "EXECUTING";
      case "verifying": return "VERIFYING";
      case "completed": return "COMPLETED";
      case "error": return "ERROR";
      case "failed": return "FAILED";
      case "approval_required": return "APPROVAL";
      default: return status.toUpperCase() || "UNKNOWN";
    }
  };

  // Size mapping
  const getSizeProps = (size) => {
    switch (size) {
      case "sm": return { width: "8px", height: "8px", fontSize: "10px" };
      case "lg": return { width: "16px", height: "16px", fontSize: "14px" };
      case "md": default: return { width: "12px", height: "12px", fontSize: "12px" };
    }
  };

  const sizeProps = getSizeProps(size);
  const statusColor = getStatusColor(status);
  const statusLabel = getStatusLabel(status);

  return (
    <div className="task-status task-status-theme" title={statusLabel}>
      <div
        className="task-status-dot"
        style={{
          width: sizeProps.width,
          height: sizeProps.height,
          backgroundColor: statusColor,
          boxShadow: `0 0 8px ${statusColor}`,
        }}
      />
      <span className="task-status-label" style={{ fontSize: sizeProps.fontSize }}>
        {statusLabel}
      </span>
    </div>
  );
}