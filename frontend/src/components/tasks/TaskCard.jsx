import React, { useState } from "react";
import TaskStatus from "./TaskStatus";
import ExecutionStep from "./ExecutionStep";
import TechnicalDetails from "./TechnicalDetails";

/**
 * TaskCard - Compact task result display with expandable technical details
 * Shows task description, status, and optional expandable details panel
 */
export default function TaskCard({ 
  task, 
  onTaskAction 
}) {
  const [showDetails, setShowDetails] = useState(false);
  
  // Extract task properties with sensible defaults
  const {
    id,
    description = "Task executed",
    status = "completed",
    result = "",
    tool = "unknown",
    parse_ok = false,
    source = "UNKNOWN",
    steps = [],
    technicalDetails = {}
  } = task;

  // Format result for display
  const getResultDisplay = (result) => {
    if (!result) return "No result";
    
    // If it's an object, try to extract meaningful info
    if (typeof result === "object" && result !== null) {
      // Handle common result types
      if (result.success !== undefined) {
        return result.success ? "Success" : "Failed";
      }
      
      if (result.exists !== undefined) {
        return result.exists ? "File exists" : "File not found";
      }
      
      if (result.content && typeof result.content === "string") {
        // Truncate long content
        return result.content.length > 100 
          ? `${result.content.substring(0, 100)}...` 
          : result.content;
      }
      
      // Fallback to JSON string (truncated)
      const jsonStr = JSON.stringify(result, null, 2);
      return jsonStr.length > 100 
        ? `${jsonStr.substring(0, 100)}...` 
        : jsonStr;
    }
    
    // String result
    return String(result).length > 100 
      ? `${String(result).substring(0, 100)}...` 
      : String(result);
  };

  return (
    <div className="task-card task-card-theme">
      {/* Task Header */}
      <div className="task-card-header">
        <div className="task-icon">
          <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="10" strokeDasharray="4 2" />
            <path d="M12 8v4l2 2" />
          </svg>
        </div>
        
        <div className="task-info">
          <h3 className="task-title">{description}</h3>
          <div className="task-meta">
            <TaskStatus status={status} size="sm" />
            <span className="task-tool">• {tool.toUpperCase()}</span>
            <span className="task-source">• {source}</span>
          </div>
        </div>
        
        {/* Action Button (for approval/retry etc.) */}
        {onTaskAction && (
          <button 
            className="task-action-btn" 
            onClick={() => onTaskAction(id)}
            aria-label="Task action"
          >
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.5">
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="8" y1="12" x2="12" y2="12" />
            </svg>
          </button>
        )}
      </div>
      
      {/* Result Display */}
      <div className="task-result">
        <p className="task-result-label">RESULT:</p>
        <div className="task-result-value">
          {getResultDisplay(result)}
          {parse_ok === false && (
            <span className="task-result-warning">⚠ Parse issues</span>
          )}
        </div>
      </div>
      
      {/* Execution Steps (if available) */}
      {steps && steps.length > 0 && (
        <div className="task-steps">
          <h3 className="task-section-title">EXECUTION STEPS:</h3>
          <div className="task-steps-list">
            {steps.map((step, index) => (
              <ExecutionStep 
                key={index} 
                step={step} 
                index={index + 1} 
              />
            ))}
          </div>
        </div>
      )}
      
      {/* Toggle Details Button */}
      <button 
        className="task-toggle-details" 
        onClick={() => setShowDetails(!showDetails)}
        aria-label={showDetails ? "Hide technical details" : "Show technical details"}
      >
        <span className="task-toggle-label">
          {showDetails ? "Hide" : "Show"} Technical Details
        </span>
        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.5">
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </button>
      
      {/* Expandable Technical Details Panel */}
      {showDetails && (
        <div className="task-details-panel">
          <TechnicalDetails 
            task={task} 
            onClose={() => setShowDetails(false)}
          />
        </div>
      )}
    </div>
  );
}