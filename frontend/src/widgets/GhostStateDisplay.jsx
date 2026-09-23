import React from "react";
import { GHOST_STATES } from "../../utils/constants";

/**
 * GhostStateDisplay - Visual indicator of current GHOST system state
 * Shows a pulsing core with state-based color and label
 */
export default function GhostStateDisplay({ state = GHOST_STATES.IDLE }) {
  // State to color mapping
  const getStateColor = (state) => {
    switch (state) {
      case GHOST_STATES.IDLE:
        return "var(--color-state-idle)";
      case GHOST_STATES.LISTENING:
      case GHOST_STATES.THINKING:
        return "var(--color-state-listening)";
      case GHOST_STATES.PLANNING:
        return "var(--color-state-planning)";
      case GHOST_STATES.EXECUTING:
        return "var(--color-state-executing)";
      case GHOST_STATES.VERIFYING:
        return "var(--color-state-verifying)";
      case GHOST_STATES.COMPLETED:
        return "var(--color-state-completed)";
      case GHOST_STATES.ERROR:
      case GHOST_STATES.APPROVAL_REQUIRED:
        return "var(--color-state-error)";
      default:
        return "var(--color-state-idle)";
    }
  };

  // State to label mapping
  const getStateLabel = (state) => {
    switch (state) {
      case GHOST_STATES.IDLE:
        return "IDLE";
      case GHOST_STATES.LISTENING:
        return "LISTENING";
      case GHOST_STATES.THINKING:
        return "THINKING";
      case GHOST_STATES.PLANNING:
        return "PLANNING";
      case GHOST_STATES.EXECUTING:
        return "EXECUTING";
      case GHOST_STATES.VERIFYING:
        return "VERIFYING";
      case GHOST_STATES.COMPLETED:
        return "COMPLETED";
      case GHOST_STATES.ERROR:
        return "ERROR";
      case GHOST_STATES.APPROVAL_REQUIRED:
        return "APPROVAL";
      default:
        return state.toUpperCase();
    }
  };

  return (
    <div className="ghost-state-display ghost-state-display-theme" title={getStateLabel(state)}>
      <div
        className="ghost-state-dot"
        style={{
          backgroundColor: getStateColor(state),
          boxShadow: `0 0 12px ${getStateColor(state)}`,
        }}
      />
      <div className="ghost-state-label">{getStateLabel(state)}</div>
    </div>
  );
}