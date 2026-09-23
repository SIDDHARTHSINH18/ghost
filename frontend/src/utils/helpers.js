/**
 * Utility helper functions for the GHOST frontend
 */

/**
 * Safely read and parse JSON from localStorage
 * @param {string} key - localStorage key
 * @param {*} fallback - Fallback value if parsing fails
 * @returns {*} - Parsed value or fallback
 */
export const readJSON = (key, fallback) => {
  try {
    const value = localStorage.getItem(key);
    return value ? JSON.parse(value) : fallback;
  } catch {
    return fallback;
  }
};

/**
 * Safely save JSON to localStorage
 * @param {string} key - localStorage key
 * @param {*} value - Value to save
 */
export const saveJSON = (key, value) => {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // Best effort
  }
};

/**
 * Create a stable hash from a string
 * @param {string} value - Input string
 * @returns {number} - Hash value
 */
export const stableHash = (value = "") => {
  let hash = 2166136261;

  for (let i = 0; i < value.length; i += 1) {
    hash ^= value.charCodeAt(i);
    hash = Math.imul(hash, 16777619);
  }

  return Math.abs(hash >>> 0);
};

/**
 * Create a stable position for a node in the graph
 * @param {Object} node - Node data
 * @param {number} index - Index of node among its type
 * @param {number} total - Total number of nodes of this type
 * @param {Object} zones - Positioning zones for node types
 * @returns {Object} - Node with position data
 */
export const createStablePosition = (node, index, total, zones) => {
  if (node.type === "ghost") {
    return {
      ...node,
      x: 0,
      y: 0,
      fx: 0,
      fy: 0,
    };
  }

  const [cx, cy] = zones[node.type] || [0, 0];

  const hash = stableHash(
    String(node.id || node.label || index)
  );

  const angle =
    (index / Math.max(total, 1)) *
      Math.PI *
      2 +
    ((hash % 100) / 100) * 0.55;

  const radius =
    90 +
    (hash % 90) +
    (index % 4) * 22;

  const x =
    cx +
    Math.cos(angle) * radius;

  const y =
    cy +
    Math.sin(angle) *
      radius *
      0.72;

  return {
    ...node,
    x,
    y,
    fx: x,
    fy: y,
  };
};

// Display-only product identity remap. The backend graph still
// emits the legacy name in its core/project labels and generated
// descriptions; ids, types and user data (filenames, memory and
// task labels) stay untouched so selection logic and the API
// contract keep working.
const DISPLAY_LABELS = {
  GHOST: "ENMA",
};

const DISPLAY_DESCRIPTIONS = {
  "Indexed document available to GHOST.":
    "Indexed document available to ENMA.",
  "GHOST's persistent conversation memory.":
    "ENMA's persistent conversation memory.",
  "GHOST personal AI operating system.":
    "ENMA personal AI operating system.",
  "GHOST task execution system.":
    "ENMA task execution system.",
};

const remapDisplay = (table, value) =>
  typeof value === "string" && Object.hasOwn(table, value)
    ? table[value]
    : value;

/**
 * Build visual graph with stable positions from raw graph data
 *
 * Normalizes every backend node into the stable internal shape:
 *   { id, type, label, data, metadata }
 * where `data` carries the real backend payload (description,
 * status, memory_id, task_id, size, ...) and `metadata` carries
 * view-derived structural facts (root emphasis, link degree).
 * All original backend fields stay on the node top level so the
 * existing renderer/inspector fields keep working.
 *
 * @param {Object} graphData - Raw graph data from API (nodes + links/edges)
 * @param {Object} storedLayout - Previously stored layout from localStorage
 * @param {Object} zones - Positioning zones for node types
 * @returns {Object} - Processed graph with positions
 */
export const buildVisualGraph = (graphData, storedLayout = {}, zones) => {
  const rawNodes = graphData.nodes || [];
  const rawLinks = graphData.links || [];

  // Real structural fact per node: how many edges touch it.
  const degreeById = new Map();

  rawLinks.forEach((link) => {
    const sourceId =
      typeof link.source === "object" ? link.source.id : link.source;
    const targetId =
      typeof link.target === "object" ? link.target.id : link.target;

    if (sourceId === undefined || targetId === undefined) return;

    degreeById.set(sourceId, (degreeById.get(sourceId) || 0) + 1);
    degreeById.set(targetId, (degreeById.get(targetId) || 0) + 1);
  });

  const counts = {};

  const nodes = rawNodes.map((node) => {
    // Normalize type casing: the backend may send "GHOST"
    // while the frontend color/zone tables use lowercase keys.
    const type = String(
      node.type || "system"
    ).toLowerCase();

    counts[type] =
      (counts[type] || 0) + 1;

    // Hub nodes (memory-root, tasks-root, project-*)
    // receive the root emphasis treatment in the renderer.
    const nodeId = String(
      node.id || ""
    );

    const isRoot =
      Boolean(node.isRoot) ||
      nodeId.endsWith("-root") ||
      nodeId.startsWith("project-");

    // Real backend payload without the identity fields.
    const data = { ...node };
    delete data.id;
    delete data.label;
    delete data.type;

    return {
      ...node,
      label: remapDisplay(DISPLAY_LABELS, node.label),
      description: remapDisplay(DISPLAY_DESCRIPTIONS, node.description),
      type,
      isRoot,
      data,
      metadata: {
        isRoot,
        degree: degreeById.get(node.id) || 0,
      },
    };
  });

  const indexes = {};

  const placedNodes = nodes.map(
    (node) => {
      if (storedLayout[node.id]) {
        return {
          ...node,
          x: storedLayout[node.id].x,
          y: storedLayout[node.id].y,
          fx: storedLayout[node.id].x,
          fy: storedLayout[node.id].y,
        };
      }

      const index =
        indexes[node.type] || 0;

      indexes[node.type] =
        index + 1;

      return createStablePosition(
        node,
        index,
        counts[node.type] || 1,
        zones
      );
    }
  );

  return {
    nodes: placedNodes,
    links: (
      graphData.links || []
    ).map((edge) => ({
      ...edge,
    })),
  };
};

/**
 * Clean Mermaid source to prevent common LLM-generated issues
 * @param {string} source - Raw Mermaid source
 * @returns {string} - Cleaned Mermaid source
 */
export const cleanMermaidSource = (source = "") => {
  let value = source.replace(/\r\n/g, "\n").trim();

  // Remove HTML that commonly breaks Mermaid parsing when generated by an LLM.
  value = value
    .replace(/<br\s*\/?>/gi, " ")
    .replace(/<br\s*>/gi, " ")
    .replace(/<\/?div[^>]*>/gi, " ")
    .replace(/<\/?span[^>]*>/gi, " ")
    .replace(/&nbsp;/gi, " ")
    .replace(/&/gi, "&")
    .replace(/"/gi, '"');

  // Mermaid comments are safe, but model-generated markdown comments are not.
  value = value.replace(/^\s*```(?:mermaid)?\s*$/gim, "");
  value = value.replace(/^\s*```\s*$/gim, "");

  // Repair a few common LLM mistakes in class declarations.
  value = value.replace(
    /^\s*class\s+([^;]+?)\s*;\s*$/gm,
    (_, body) => `class ${body.trim()}`
  );

  // Keep Mermaid labels readable and avoid accidental nested square brackets.
  value = value.replace(/\[([^\[\]\n]*?)\[([^\[\]\n]*?)\]([^\[\]\n]*?)\]/g, (_, a, b, c) => {
    const label = `${a} ${b} ${c}`.replace(/\s+/g, " ").trim();
    return `[${label}]`;
  });

  // Remove unsupported styling directives that are frequently emitted with raw Mermaid.
  value = value.replace(/^\s*style\s+[^\n]*$/gim, "");
  value = value.replace(/^\s*classDef\s+[^\n]*$/gim, "");

  return value.trim();
};

/**
 * Format page numbers into ranges for display
 * @param {Array} pages - Array of page numbers
 * @returns {Array} - Formatted page ranges (e.g., ["P.1", "P.3-5"])
 */
export const formatSourcePages = (pages = []) => {
  if (!pages || pages.length === 0) return [];

  const sortedPages = [...new Set(
    pages
      .map(Number)
      .filter(Number.isFinite)
  )].sort((a, b) => a - b);

  const ranges = [];
  let start = sortedPages[0];
  let previous = sortedPages[0];

  for (let i = 1; i < sortedPages.length; i++) {
    const current = sortedPages[i];

    if (current === previous + 1) {
      previous = current;
      continue;
    }

    ranges.push(
      start === previous
        ? `P.${start}`
        : `P.${start}–${previous}`
    );

    start = current;
    previous = current;
  }

  ranges.push(
    start === previous
      ? `P.${start}`
      : `P.${start}–${previous}`
  );

  return ranges;
};

/**
 * Format a numeric score to 2 decimal places
 * @param {*} value - Value to format
 * @returns {string} - Formatted score or "—"
 */
export const formatScore = (value) => {
  const number = Number(value);
  return Number.isFinite(number) ? number.toFixed(2) : "—";
};

/**
 * Format a timestamp to local string
 * @param {*} value - Timestamp value
 * @returns {string} - Formatted date/time or "—"
 */
export const formatDateTime = (value) => {
  if (!value) return "—";

  try {
    return new Date(value).toLocaleString();
  } catch {
    return String(value);
  }
};

/**
 * Format bytes to human-readable format
 * @param {*} bytes - Byte value
 * @returns {string} - Formatted size (e.g., "1.5 KB")
 */
export const formatBytes = (bytes) => {
  const number = Number(bytes);

  if (!Number.isFinite(number)) return "—";
  if (number < 1024) return `${number} B`;
  if (number < 1024 * 1024) return `${(number / 1024).toFixed(1)} KB`;

  return `${(number / (1024 * 1024)).toFixed(1)} MB`;
};

/**
 * Find a memory node that matches the selected node's real memory id
 * (graph memory nodes carry the backend UUID as `memory_id`), falling
 * back to node id and label matching.
 * @param {Object} selectedNode - The currently selected node
 * @param {Array} memoryItems - Array of memory items from backend
 * @returns {Object|null} - Matching memory item or null
 */
export const resolveMemoryNode = (selectedNode, memoryItems) => {
  if (!selectedNode || !memoryItems || !memoryItems.length) return null;

  // Match by the real memory id carried on the graph node
  // (set by the backend /api/graph as `memory_id`).
  const memoryId =
    selectedNode.memory_id ||
    (typeof selectedNode.id === "string" &&
    selectedNode.id.startsWith("memory-")
      ? selectedNode.id.slice("memory-".length)
      : null);

  if (memoryId) {
    const match = memoryItems.find(
      (memory) => memory.id === memoryId
    );
    if (match) return match;
  }

  // Try to match by ID first
  if (selectedNode.id) {
    const match = memoryItems.find(memory => memory.id === selectedNode.id);
    if (match) return match;
  }

  // Try to match by label/content
  if (selectedNode.label) {
    const match = memoryItems.find(memory =>
      memory.content && memory.content.includes(selectedNode.label)
    );
    if (match) return match;
  }

  return null;
};