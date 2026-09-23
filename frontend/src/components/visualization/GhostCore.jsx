import React, { useEffect, useState } from "react";
import { GHOST_STATES } from "../../utils/constants";

/**
 * GhostCore - Central pulsating visualization with orbiting elements
 * Displays the GHOST core with state-based color and animation changes
 */
export default function GhostCore({ state = GHOST_STATES.IDLE }) {
  // Determine core color based on state
  const getCoreColor = (state) => {
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

  // Determine pulse speed based on state (faster when active)
  const getPulseSpeed = (state) => {
    switch (state) {
      case GHOST_STATES.IDLE:
        return "4s";
      case GHOST_STATES.LISTENING:
      case GHOST_STATES.THINKING:
        return "2.5s";
      case GHOST_STATES.PLANNING:
        return "3s";
      case GHOST_STATES.EXECUTING:
        return "1.8s";
      case GHOST_STATES.VERIFYING:
        return "2.2s";
      case GHOST_STATES.COMPLETED:
        return "3s";
      case GHOST_STATES.ERROR:
      case GHOST_STATES.APPROVAL_REQUIRED:
        return "1.5s";
      default:
        return "4s";
    }
  };

  // Determine orbit speed based on state
  const getOrbitSpeed = (state) => {
    switch (state) {
      case GHOST_STATES.IDLE:
        return "20s";
      case GHOST_STATES.LISTENING:
      case GHOST_STATES.THINKING:
        return "12s";
      case GHOST_STATES.PLANNING:
        return "15s";
      case GHOST_STATES.EXECUTING:
        return "10s";
      case GHOST_STATES.VERIFYING:
        return "11s";
      case GHOST_STATES.COMPLETED:
        return "18s";
      case GHOST_STATES.ERROR:
      case GHOST_STATES.APPROVAL_REQUIRED:
        return "8s";
      default:
        return "20s";
    }
  };

  return (
    <section className="ghost-core">
      <div className="core-orbit orbit-a" />
      <div className="core-orbit orbit-b" />
      <div className="core-orbit orbit-c" />
      <div className="core-ticks">
        {Array.from({ length: 8 }).map((_, index) => (
          <i key={index} />
        ))}
      </div>
      <div className={`core-disc core-${state.toLowerCase()}`}>
        <div className="core-glow" />
        <div className="core-inner">
          <div className="core-name">G.H.O.S.T.</div>
          <div className="core-line" />
          <div className="core-state">{state}</div>
        </div>
      </div>
      <div className="core-status">
        <span className="core-status-dot" />
        {state}
      </div>
      <div className="core-hint">NEURAL CORE</div>
    </section>
  );
}