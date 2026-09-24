
/**
 * RailNavigator - compact workspace navigation rail.
 *
 * GHOST workspaces: Mind (knowledge graph home), Chat, plus
 * drawer-backed knowledge spaces (Tasks, Documents, Memory).
 * Skills and Settings have no views yet and render disabled
 * rather than pretending to work.
 */
export default function RailNavigator({ activeTab, onTabChange }) {
  const navItems = [
    {
      id: "mind",
      label: "Mind",
      icon: (
        <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.8">
          <circle cx="12" cy="12" r="2.2" />
          <circle cx="5.5" cy="7" r="1.7" />
          <circle cx="18.5" cy="7" r="1.7" />
          <circle cx="6.5" cy="17.5" r="1.7" />
          <circle cx="17.5" cy="17.5" r="1.7" />
          <path d="M7 8.2l3 2.4M17 8.2l-3 2.4M7.6 16.4l2.8-2.6M16.4 16.4l-2.8-2.6" />
        </svg>
      ),
    },
    {
      id: "chat",
      label: "Chat",
      icon: (
        <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.8">
          <path d="M21 14a2 2 0 0 1-2 2H8l-4 4V5a2 2 0 0 1 2-2h13a2 2 0 0 1 2 2z" />
        </svg>
      ),
    },
    {
      id: "tasks",
      label: "Tasks",
      icon: (
        <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.8">
          <path d="M9 6h11M9 12h11M9 18h11" />
          <path d="M4 6l1 1 2-2M4 12l1 1 2-2M4 18l1 1 2-2" />
        </svg>
      ),
    },
    {
      id: "documents",
      label: "Documents",
      icon: (
        <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.8">
          <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
          <polyline points="14 2 14 8 20 8" />
          <line x1="9" y1="13" x2="15" y2="13" />
          <line x1="9" y1="17" x2="15" y2="17" />
        </svg>
      ),
    },
    {
      id: "memory",
      label: "Memory",
      icon: (
        <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.8">
          <path d="M12 4a4.5 4.5 0 0 0-4.4 3.6A4 4 0 0 0 5 15.4 4.2 4.2 0 0 0 9 20a4.4 4.4 0 0 0 3-1.2A4.4 4.4 0 0 0 15 20a4.2 4.2 0 0 0 4-4.6 4 4 0 0 0-2.6-7.8A4.5 4.5 0 0 0 12 4z" />
          <path d="M12 4v14.8M8.5 11h7M9.5 16h5" />
        </svg>
      ),
    },
    {
      id: "skills",
      label: "Skills",
      disabled: true,
      icon: (
        <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.8">
          <path d="M12 3l2.2 5.3L20 9l-4.4 3.6L17 19l-5-3.2L7 19l1.4-6.4L4 9l5.8-.7z" />
        </svg>
      ),
    },
    {
      id: "settings",
      label: "Settings",
      disabled: true,
      icon: (
        <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.8">
          <circle cx="12" cy="12" r="3" />
          <path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1a2 2 0 1 1-2.9 2.9l-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1a2 2 0 1 1-2.9-2.9l.1-.1a1.7 1.7 0 0 0 .3-1.9 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9l-.1-.1a2 2 0 1 1 2.9-2.9l.1.1a1.7 1.7 0 0 0 1.9.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.9-.3l.1-.1a2 2 0 1 1 2.9 2.9l-.1.1a1.7 1.7 0 0 0-.3 1.9v.1a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z" />
        </svg>
      ),
    },
  ];

  return (
    <div className="nav-rail nav-rail-theme">
      {/* Branding top node */}
      <div className="rail-brand">
        <div className="rail-brand-inner">
          E
        </div>
      </div>

      <div className="rail-separator" />

      {/* Nav items list */}
      <div className="rail-items">
        {navItems.map((item) => {
          const isActive = activeTab === item.id;
          return (
            <button
              key={item.id}
              className={`rail-button ${isActive ? "active" : ""} ${item.disabled ? "disabled" : ""}`}
              onClick={() => !item.disabled && onTabChange(item.id)}
              disabled={Boolean(item.disabled)}
              title={item.disabled ? `${item.label} — not available yet` : item.label}
              aria-label={item.label}
            >
              <div className="rail-button-icon">
                {item.icon}
              </div>

              <span className="rail-label">{item.label}</span>
            </button>
          );
        })}
      </div>

      <div className="rail-footer">
        <div className="rail-status-dot" />
      </div>
    </div>
  );
}
