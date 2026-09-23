import React from "react";
import { formatDateTime, formatBytes, formatScore } from "../../utils/helpers";

/**
 * TechnicalDetails - Expandable panel showing full task execution data
 * Displays comprehensive information about task execution for debugging
 */
export default function TechnicalDetails({ task, onClose }) {
  const {
    id,
    description,
    status,
    result,
    tool,
    parse_ok,
    source,
    startTime,
    endTime,
    steps = [],
    inputs = {},
    outputs = {},
    metadata = {}
  } = task;

  return (
    <div className="technical-details technical-details-theme">
      {/* Panel Header */}
      <div className="technical-details-header">
        <button className="technical-details-close" onClick={onClose} aria-label="Close details">
          <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2">
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>
        <h2 className="technical-details-title">
          TASK EXECUTION DETAILS
          <span className="technical-details-id">#{id}</span>
        </h2>
      </div>
      
      {/* Details Content */}
      <div className="technical-details-content">
        {/* Basic Info */}
        <div className="technical-details-section">
          <h3 className="technical-details-section-title">BASIC INFORMATION</h3>
          <div className="technical-details-grid">
            <div className="technical-details-item">
              <span className="technical-details-label">DESCRIPTION</span>
              <span className="technical-details-value">{description}</span>
            </div>
            <div className="technical-details-item">
              <span className="technical-details-label">STATUS</span>
              <span className="technical-details-value" 
                style={{
                  color: 
                    status === "completed" ? "var(--color-state-completed)" :
                    status === "failed" || status === "error" ? "var(--color-state-error)" :
                    status === "running" || status === "executing" ? "var(--color-state-executing)" :
                    "var(--color-state-idle)"
                }}
              >
                {status.toUpperCase()}
              </span>
            </div>
            <div className="technical-details-item">
              <span className="technical-details-label">TOOL</span>
              <span className="technical-details-value">{tool.toUpperCase()}</span>
            </div>
            <div className="technical-details-item">
              <span className="technical-details-label">SOURCE</span>
              <span className="technical-details-value">{source}</span>
            </div>
            <div className="technical-details-item">
              <span className="technical-details-label">PARSE OK</span>
              <span className="technical-details-value">
                {parse_ok ? "YES" : "NO"}
              </span>
            </div>
            <div className="technical-details-item">
              <span className="technical-details-label">START TIME</span>
              <span className="technical-details-value">
                {formatDateTime(startTime)}
              </span>
            </div>
            <div className="technical-details-item">
              <span className="technical-details-label">END TIME</span>
              <span className="technical-details-value">
                {formatDateTime(endTime)}
              </span>
            </div>
          </div>
        </div>
        
        {/* Inputs */}
        {inputs && Object.keys(inputs).length > 0 && (
          <div className="technical-details-section">
            <h3 className="technical-details-section-title">INPUTS</h3>
            <div className="technical-details-json">
              <pre className="json-viewer">{JSON.stringify(inputs, null, 2)}</pre>
            </div>
          </div>
        )}
        
        {/* Outputs / Results */}
        {outputs && Object.keys(outputs).length > 0 && (
          <div className="technical-details-section">
            <h3 className="technical-details-section-title">OUTPUTS</h3>
            <div className="technical-details-json">
              <pre className="json-viewer">{JSON.stringify(outputs, null, 2)}</pre>
            </div>
          </div>
        )}
        
        {/* Full Result */}
        {result && (
          <div className="technical-details-section">
            <h3 className="technical-details-section-title">FULL RESULT</h3>
            <div className="technical-details-json">
              <pre className="json-viewer">
                {typeof result === "string" 
                  ? result 
                  : JSON.stringify(result, null, 2)
                }
              </pre>
            </div>
          </div>
        )}
        
        {/* Execution Steps */}
        {steps && steps.length > 0 && (
          <div className="technical-details-section">
            <h3 className="technical-details-section-title">EXECUTION STEPS</h3>
            <div className="technical-details-steps">
              {steps.map((step, index) => (
                <div key={index} className="technical-details-step">
                  <div className="technical-details-step-header">
                    <span className="technical-details-step-number">{index + 1}</span>
                    <span className="technical-details-step-tool">
                      {step.tool ? `[${step.tool.toUpperCase()}]` : ""}
                    </span>
                    <span className="technical-details-step-status"
                      style={{
                        color: 
                          step.status === "completed" ? "var(--color-state-completed)" :
                          step.status === "failed" || step.status === "error" ? "var(--color-state-error)" :
                          step.status === "running" || step.status === "executing" ? "var(--color-state-executing)" :
                          "var(--color-state-idle)"
                      }}
                    >
                      {step.status.toUpperCase()}
                    </span>
                  </div>
                  <div className="technical-details-step-description">
                    {step.description}
                  </div>
                  {step.result && (
                    <div className="technical-details-step-result">
                      <span className="technical-details-step-result-label">RESULT:</span>
                      <span className="technical-details-step-result-value">
                        {typeof step.result === "string"
                          ? step.result.length > 200
                            ? `${step.result.substring(0, 200)}...`
                            : step.result
                          : JSON.stringify(step.result).length > 200
                            ? `${JSON.stringify(step.result).substring(0, 200)}...`
                            : JSON.stringify(step.result)
                        }
                      </span>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
        
        {/* Metadata */}
        {metadata && Object.keys(metadata).length > 0 && (
          <div className="technical-details-section">
            <h3 className="technical-details-section-title">METADATA</h3>
            <div className="technical-details-grid">
              {Object.entries(metadata).map(([key, value], index) => (
                <div key={index} className="technical-details-item">
                  <span className="technical-details-label">{key.toUpperCase()}</span>
                  <span className="technical-details-value">
                    {typeof value === "object"
                      ? JSON.stringify(value)
                      : String(value)
                    }
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
      
      {/* Panel Footer */}
      <div className="technical-details-footer">
        <span className="technical-details-timestamp">
          GENERATED: {formatDateTime(Date.now())}
        </span>
        <button className="technical-details-close-btn" onClick={onClose}>
          CLOSE PANEL
        </button>
      </div>
    </div>
  );
}