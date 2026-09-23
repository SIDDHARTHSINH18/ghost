import { memo } from "react";
import {
  formatBytes,
  formatDateTime,
  formatScore,
} from "../../utils/helpers";

/**
 * NodeInspector - right-panel contextual view for the selected
 * graph node. Renders only REAL data: the node's backend payload
 * (node.data), the resolved memory item from the memory API, the
 * task detail from the tasks API, provider/system info for the
 * GHOST core, and the node's real edges.
 */
function NodeInspector({
  node,
  memoryItem = null,
  taskDetail = null,
  systemInfo = null,
  nodeCounts = {},
  connections = [],
  onOpenNode = () => {},
  onClose = () => {},
}) {
  if (!node) {
    return (
      <div className="node-inspector-empty">
        <div className="node-inspector-icon">🔍</div>
        <p className="node-inspector-message">Select a node to inspect</p>
      </div>
    );
  }

  const type = node.type || "system";

  const getNodeTypeColor = (nodeType) => {
    switch (nodeType) {
      case "ghost": return "var(--node-type-ghost)";
      case "document": return "var(--node-type-document)";
      case "memory": return "var(--node-type-memory)";
      case "project": return "var(--node-type-project)";
      case "task": return "var(--node-type-task)";
      case "tool": return "var(--node-type-tool)";
      case "system": return "var(--node-type-system)";
      default: return "var(--node-type-unknown)";
    }
  };

  const rows = (entries) =>
    entries
      .filter(([, value]) => value !== undefined && value !== null && value !== "")
      .map(([key, value]) => (
        <div key={key} className="node-inspector-property">
          <span className="node-inspector-property-name">{key}</span>
          <span className="node-inspector-property-value">{value}</span>
        </div>
      ));

  // --- Type-specific REAL data sections ------------------------------

  let sections;

  if (type === "ghost") {
    sections = [
      {
        title: "SYSTEM",
        content: node.description || "Personal AI operating system.",
      },
      {
        title: "CORE",
        rows: rows([
          ["MODEL", systemInfo?.model || "—"],
          ["PROVIDER", systemInfo?.providerOnline ? "ONLINE" : "OFFLINE"],
        ]),
      },
      {
        title: "GRAPH COMPOSITION",
        rows: rows([
          ["DOCUMENTS", nodeCounts.document ?? 0],
          ["MEMORIES", nodeCounts.memory ?? 0],
          ["PROJECTS", nodeCounts.project ?? 0],
          ["TASKS", nodeCounts.task ?? 0],
          ["TOOLS", nodeCounts.tool ?? 0],
        ]),
      },
    ];
  } else if (type === "memory") {
    sections = [
      {
        title: "MEMORY",
        content: memoryItem
          ? memoryItem.content
          : "Content is available through the memory API. Open the MEMORY drawer to view and manage this memory.",
      },
      {
        title: "PROPERTIES",
        rows: rows([
          ["TYPE", (memoryItem?.type || node.memory_type || "—").toUpperCase()],
          ["IMPORTANCE", memoryItem ? formatScore(memoryItem.importance) : "—"],
          ["CONFIDENCE", memoryItem ? formatScore(memoryItem.confidence) : "—"],
          ["PROJECT", memoryItem?.project || "—"],
          ["SOURCE", memoryItem?.source || "—"],
          ["CREATED", memoryItem ? formatDateTime(memoryItem.created_at) : "—"],
          ["UPDATED", memoryItem ? formatDateTime(memoryItem.updated_at) : "—"],
        ]),
      },
      ...(memoryItem?.tags?.length
        ? [
            {
              title: "TAGS",
              tags: memoryItem.tags,
            },
          ]
        : []),
    ];
  } else if (type === "document") {
    sections = [
      {
        title: "DOCUMENT",
        content: node.description || "Indexed document available to ENMA.",
      },
      {
        title: "PROPERTIES",
        rows: rows([
          ["FILENAME", node.label],
          ["SIZE", formatBytes(node.size)],
          ["PAGES", node.pages],
          ["CHUNKS", node.chunks],
          ["STATUS", String(node.status || "—").toUpperCase()],
        ]),
      },
    ];
  } else if (type === "task") {
    sections = [
      {
        title: "TASK",
        content: taskDetail?.description || node.description,
      },
      {
        title: "PROPERTIES",
        rows: rows([
          ["STATUS", String(taskDetail?.status || node.status || "—").toUpperCase()],
          ["PRIORITY", taskDetail?.priority ?? node.priority],
          ["CREATED", formatDateTime(taskDetail?.created_at || node.created_at)],
          ["UPDATED", taskDetail ? formatDateTime(taskDetail.updated_at) : null],
          ["RESULT", taskDetail?.result || null],
          ["ERROR", taskDetail?.error || null],
        ]),
      },
    ];
  } else if (type === "project") {
    sections = [
      {
        title: "PROJECT",
        content: node.description || "Project node.",
      },
      {
        title: "PROPERTIES",
        rows: rows([
          ["NAME", node.label],
          ["NODE ID", node.id],
        ]),
      },
    ];
  } else if (type === "tool") {
    sections = [
      {
        title: "TOOL",
        content: node.description,
      },
      {
        title: "PROPERTIES",
        rows: rows([
          ["NAME", node.label],
          ["CATEGORY", node.category],
          ["RISK LEVEL", node.risk_level],
        ]),
      },
    ];
  } else {
    // Unknown / system: generic view of the real payload.
    sections = [
      ...(node.description
        ? [{ title: "DESCRIPTION", content: node.description }]
        : []),
      {
        title: "PROPERTIES",
        rows: rows(
          Object.entries(node.data || {}).map(([key, value]) => [
            key.replace(/_/g, " ").toUpperCase(),
            typeof value === "object" ? null : String(value),
          ])
        ),
      },
    ];
  }

  return (
    <div className="node-inspector node-inspector-theme">
      <div className="node-inspector-header">
        <button className="node-inspector-close" onClick={onClose} aria-label="Close inspector">
          <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2">
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>
        <div className="node-inspector-kicker">
          <span
            className="node-type-dot"
            style={{ backgroundColor: getNodeTypeColor(type) }}
          />
          {type.toUpperCase()}
        </div>
        <h2 className="node-inspector-title">
          {node.label || node.id || "Unknown Node"}
        </h2>
      </div>

      <div className="node-inspector-content">
        {sections.map((section) => (
          <div key={section.title} className="node-inspector-section">
            <h3 className="node-inspector-section-title">{section.title}</h3>
            {section.content && (
              <p className="node-inspector-text">{section.content}</p>
            )}
            {section.rows && section.rows.length > 0 && (
              <div className="node-inspector-properties">{section.rows}</div>
            )}
            {section.tags && (
              <div className="node-inspector-tags">
                {section.tags.map((tag) => (
                  <span key={tag} className="node-inspector-tag">
                    {tag}
                  </span>
                ))}
              </div>
            )}
          </div>
        ))}

        {/* Real edges touching this node */}
        {connections.length > 0 && (
          <div className="node-inspector-section">
            <h3 className="node-inspector-section-title">
              CONNECTIONS · {connections.length}
            </h3>
            <div className="node-inspector-connections">
              {connections.map((connection, index) => (
                <button
                  key={`${connection.id}-${index}`}
                  className="node-inspector-link"
                  onClick={() => onOpenNode(connection.id)}
                  title="Select this node"
                >
                  <span className="node-inspector-link-label">
                    {String(connection.type || "RELATED_TO").toUpperCase()}
                  </span>
                  <span className="node-inspector-link-target">
                    {connection.direction === "in" ? "← " : "→ "}
                    {connection.label}
                  </span>
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      <div className="node-inspector-footer">
        <span className="node-inspector-timestamp">
          NODE ID: {String(node.id || "—")}
        </span>
      </div>
    </div>
  );
}

export default memo(NodeInspector);
