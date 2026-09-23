import React, { useEffect } from "react";

/**
 * DrawerSystem - Slide-out modal drawer container
 * Wraps panels like Documents, Memory, or Settings in a high-tech frame
 */
export default function DrawerSystem({
  isOpen,
  title,
  subtitle,
  onClose,
  children,
  width = "var(--ghost-drawer-width, 410px)"
}) {
  // Close drawer on Escape key press
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === "Escape" && isOpen) {
        onClose();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <>
      {/* Drawer Overlay backdrop */}
      <div className="drawer-overlay" onClick={onClose} />

      {/* Drawer Panel Container */}
      <div
        className="drawer-panel drawer-theme"
        style={{
          width: width,
        }}
      >
        {/* Decorative Top Scanline & Borders */}
        <div className="drawer-scanner" />
        <div className="drawer-border-corner top-left" />
        <div className="drawer-border-corner top-right" />
        <div className="drawer-border-corner bottom-left" />
        <div className="drawer-border-corner bottom-right" />

        {/* Header Block */}
        <div className="drawer-header">
          <div className="drawer-header-left">
            <h2 className="drawer-title">
              {title}
              <span className="drawer-title-ticker"> //_SYS_PANEL</span>
            </h2>
            {subtitle && <p className="drawer-subtitle">{subtitle}</p>}
          </div>

          <button className="drawer-close-btn" onClick={onClose} aria-label="Close panel">
            <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2.5">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        {/* Content Area */}
        <div className="drawer-content">
          {children}
        </div>

        {/* Decorative Panel Footer */}
        <div className="drawer-footer-accent">
          <div className="drawer-footer-line" />
          <span className="drawer-system-tag">ENMA_OS v1.2 // PERSISTENT_RESOURCES</span>
        </div>
      </div>
    </>
  );
}
