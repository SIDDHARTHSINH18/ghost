import React from "react";

/**
 * ExecutionStep - Individual step in task execution flow
 * Shows step description, status, and timing information
 */
export default function ExecutionStep({ step, index }) {
  // Extract step properties
  const {
    description = `Step ${index}`,
    status = "pending",
    tool = "",
    startTime = null,
    endTime = null,
    result = {}
  } = step;

  // Calculate duration if both times available
  const getDuration = () => {
    if (!startTime || !endTime) return null;
    try {
      const start = new Date(startTime).getTime();
      const end = new Date(endTime).getTime();
      return end - start;
    } catch (e) {
      return null;
    }
  };

  const duration = getDuration();
  const durationText = duration !== null 
    ? `${duration}ms` 
    : "";

  return (
    <div className="execution-step execution-step-theme">
      {/* Step Number and Status */}
      <div className="execution-step-header">
        <div className="execution-step-number">{index}</div>
        <div className="execution-step-status">
          <span className="step-status-dot" 
            style={{
              backgroundColor: 
                status === "completed" ? "var(--color-state-completed)" :
                status === "failed" || status === "error" ? "var(--color-state-error)" :
                status === "running" || status === "executing" ? "var(--color-state-executing)" :
                "var(--color-state-idle)"
            }}
          />
          <span className="step-status-label">{status.toUpperCase()}</span>
        </div>
        {durationText && (
          <span className="step-duration">{durationText}</span>
        )}
      </div>
      
      {/* Step Description */}
      <div className="execution-step-description">
        <span className="step-tool">{tool ? `[${tool.toUpperCase()}]` : ""}</span>
        <span className="step-text">{description}</span>
      </div>
      
      {/* Step Result (if available and significant) */}
      {result && Object.keys(result).length > 0 && (
        <div className="execution-step-result">
          <span className="step-result-label">→</span>
          <span className="step-result-value">
            {typeof result === "string" 
              ? result.length > 50 
                ? `${result.substring(0, 50)}...` 
                : result
              : JSON.stringify(result).length > 50
                ? `${JSON.stringify(result).substring(0, 50)}...`
                : JSON.stringify(result)
            }
          </span>
        </div>
      )}
    </div>
  );
}