import { useMemo } from "react";
import {
  Background,
  Controls,
  Handle,
  MiniMap,
  MarkerType,
  Position,
  ReactFlow,
  ReactFlowProvider,
} from "@xyflow/react";

import "@xyflow/react/dist/style.css";
import "./ghost-flow.css";

const PALETTE = {
  user: {
    accent: "#55f1ff",
    glow: "rgba(85,241,255,.24)",
  },

  frontend: {
    accent: "#16f5a5",
    glow: "rgba(22,245,165,.20)",
  },

  backend: {
    accent: "#ff9d32",
    glow: "rgba(255,157,50,.20)",
  },

  memory: {
    accent: "#299cff",
    glow: "rgba(41,156,255,.20)",
  },

  ai: {
    accent: "#a855ff",
    glow: "rgba(168,85,255,.22)",
  },

  output: {
    accent: "#55f1ff",
    glow: "rgba(85,241,255,.20)",
  },

  default: {
    accent: "#55d9ff",
    glow: "rgba(85,217,255,.18)",
  },
};

/*
 * Mermaid control words.
 * These should never become GHOST nodes.
 */
const RESERVED_IDS = new Set([
  "end",
  "subgraph",
]);

function cleanSource(source = "") {
  return source
    .replace(/\r\n/g, "\n")
    .replace(
      /^\s*```(?:mermaid|flowchart|graph)?\s*$/gim,
      ""
    )
    .replace(
      /^\s*```\s*$/gim,
      ""
    )
    .replace(
      /<br\s*\/?\s*>/gi,
      " "
    )
    .replace(
      /<[^>]+>/g,
      " "
    )
    .replace(
      /&nbsp;/gi,
      " "
    )
    .replace(
      /&amp;/gi,
      "&"
    )
    .replace(
      /&quot;/gi,
      '"'
    )
    .replace(
      /&#39;/gi,
      "'"
    )
    .trim();
}

function isReservedId(id = "") {
  return RESERVED_IDS.has(
    String(id)
      .trim()
      .toLowerCase()
  );
}

/*
 * Convert Mermaid-style node syntax
 * into a simple GHOST node object.
 *
 * Example:
 *
 * U[User Request]
 *
 * becomes:
 *
 * {
 *   id: "U",
 *   label: "User Request"
 * }
 */
function labelFromToken(token = "") {
  const match = token.match(
    /^([A-Za-z_][\w-]*)\s*(.*)$/
  );

  if (!match) {
    return {
      id: token.trim(),
      label: token.trim(),
    };
  }

  const id = match[1];

  let label = match[2].trim();

  if (!label) {
    return {
      id,
      label: id,
    };
  }

  const pairs = [
    ["[[", "]]"],
    ["[", "]"],
    ["(", ")"],
    ["{", "}"],
  ];

  for (const [open, close] of pairs) {
    if (
      label.startsWith(open) &&
      label.endsWith(close)
    ) {
      label = label.slice(
        open.length,
        -close.length
      );

      break;
    }
  }

  label = label
    .replace(
      /[\[\]{}]/g,
      " "
    )
    .replace(
      /^"|"$/g,
      ""
    )
    .replace(
      /\s+/g,
      " "
    )
    .trim();

  return {
    id,
    label:
      label || id,
  };
}

function inferKind(label = "") {
  const value =
    label.toLowerCase();

  if (
    /user|request|input|client/.test(
      value
    )
  ) {
    return "user";
  }

  if (
    /react|frontend|interface|ui|browser/.test(
      value
    )
  ) {
    return "frontend";
  }

  if (
    /fastapi|backend|api|processor|validation|query|context|retrieval/.test(
      value
    )
  ) {
    return "backend";
  }

  if (
    /memory|database|vector|store|persist/.test(
      value
    )
  ) {
    return "memory";
  }

  if (
    /nemotron|ai|model|llm|language|inference|generator/.test(
      value
    )
  ) {
    return "ai";
  }

  if (
    /response|output|display|formatter|result/.test(
      value
    )
  ) {
    return "output";
  }

  return "default";
}

/*
 * Parse the model's Mermaid-style
 * description without using Mermaid.
 *
 * React Flow is responsible for
 * rendering the final diagram.
 */
function parseFlowchart(source = "") {
  const text =
    cleanSource(source);

  const lines =
    text.split("\n");

  const nodeMap =
    new Map();

  const edges = [];

  let direction = "TD";

  function register(
    id,
    label
  ) {
    if (!id) {
      return;
    }

    if (
      isReservedId(id)
    ) {
      return;
    }

    const existing =
      nodeMap.get(id);

    nodeMap.set(id, {
      id,

      label:
        existing?.label ||
        label ||
        id,

      kind:
        existing?.kind ||
        inferKind(
          label || id
        ),
    });
  }

  function registerToken(
    token
  ) {
    const parsed =
      labelFromToken(
        token
      );

    if (
      !parsed.id ||
      isReservedId(
        parsed.id
      )
    ) {
      return null;
    }

    register(
      parsed.id,
      parsed.label
    );

    return parsed.id;
  }

  for (
    const rawLine of lines
  ) {
    let line =
      rawLine.trim();

    if (!line) {
      continue;
    }

    if (
      line.startsWith("%%")
    ) {
      continue;
    }

    /*
     * Read the requested Mermaid
     * direction, but GHOST may later
     * choose a better layout.
     */
    const directionMatch =
      line.match(
        /^(flowchart|graph)\s+(TD|TB|LR|RL|BT)/i
      );

    if (directionMatch) {
      direction =
        directionMatch[2]
          .toUpperCase();

      continue;
    }

    /*
     * Ignore Mermaid structural
     * configuration.
     */
    if (
      /^(subgraph|end|classDef|class|style|click|linkStyle)\b/i.test(
        line
      )
    ) {
      continue;
    }

    line =
      line.replace(
        /;\s*$/,
        ""
      );

    /*
     * Common Mermaid-style edges.
     */
    const edgeRegex =
      /([A-Za-z_][\w-]*(?:\s*(?:\[[^\n\]]*\]|\([^\n)]*\)|\{[^\n}]*\}))?)\s*(?:-->|---|==>|-.->|-\.?->)\s*(?:\|([^|]*)\|\s*)?([A-Za-z_][\w-]*(?:\s*(?:\[[^\n\]]*\]|\([^\n)]*\)|\{[^\n}]*\}))?)/g;

    let matched =
      false;

    let match;

    while (
      (match =
        edgeRegex.exec(
          line
        ))
    ) {
      matched = true;

      const sourceId =
        registerToken(
          match[1]
        );

      const targetId =
        registerToken(
          match[3]
        );

      if (
        sourceId &&
        targetId
      ) {
        edges.push({
          id:
            `e-${sourceId}-${targetId}-${edges.length}`,

          source:
            sourceId,

          target:
            targetId,

          label:
            match[2]?.trim() ||
            "",
        });
      }
    }

    /*
     * Search for standalone nodes
     * if no edge was found.
     */
    if (!matched) {
      const nodeRegex =
        /([A-Za-z_][\w-]*)\s*(\[[^\n\]]*\]|\([^\n)]*\)|\{[^\n}]*\})/g;

      let nodeMatch;

      while (
        (nodeMatch =
          nodeRegex.exec(
            line
          ))
      ) {
        const parsed =
          labelFromToken(
            nodeMatch[0]
          );

        register(
          parsed.id,
          parsed.label
        );
      }
    }
  }

  const nodes =
    Array.from(
      nodeMap.values()
    );

  /*
   * If the model returned nodes
   * without edges, connect them in
   * their original order.
   */
  if (
    nodes.length > 1 &&
    edges.length === 0
  ) {
    for (
      let index = 0;
      index <
      nodes.length - 1;
      index += 1
    ) {
      edges.push({
        id:
          `e-fallback-${index}`,

        source:
          nodes[index].id,

        target:
          nodes[
            index + 1
          ].id,

        label: "",
      });
    }
  }

  const validNodeIds =
    new Set(
      nodes.map(
        (node) =>
          node.id
      )
    );

  const cleanEdges =
    edges.filter(
      (edge) =>
        validNodeIds.has(
          edge.source
        ) &&
        validNodeIds.has(
          edge.target
        )
    );

  return {
    nodes,
    edges:
      cleanEdges,
    direction,
  };
}

/*
 * ------------------------------------------------------------------
 * GHOST BRAIN LAYOUT
 * ------------------------------------------------------------------
 *
 * Instead of simply putting every node
 * into one long vertical or horizontal
 * line, we calculate logical layers.
 *
 * Example:
 *
 *                 USER
 *                   |
 *                FRONTEND
 *                   |
 *                BACKEND
 *                   |
 *          +--------+--------+
 *          |                 |
 *        MEMORY           DOCUMENT
 *          |                 |
 *          +--------+--------+
 *                   |
 *                NEMOTRON
 *                   |
 *                RESPONSE
 *
 * This makes the visualization feel
 * like a neural architecture rather
 * than a traditional flowchart.
 */
function buildBrainLayout(
  parsed
) {
  const {
    nodes: rawNodes,
    edges,
  } = parsed;

  if (!rawNodes.length) {
    return {
      nodes: [],
      edges: [],
    };
  }

  /*
   * Build graph relationships.
   */
  const incoming =
    new Map();

  const outgoing =
    new Map();

  rawNodes.forEach(
    (node) => {
      incoming.set(
        node.id,
        0
      );

      outgoing.set(
        node.id,
        []
      );
    }
  );

  edges.forEach(
    (edge) => {
      if (
        !incoming.has(
          edge.target
        ) ||
        !outgoing.has(
          edge.source
        )
      ) {
        return;
      }

      incoming.set(
        edge.target,
        incoming.get(
          edge.target
        ) + 1
      );

      outgoing
        .get(edge.source)
        .push(
          edge.target
        );
    }
  );

  /*
   * Nodes with no incoming edges
   * become the starting layer.
   */
  let roots =
    rawNodes
      .filter(
        (node) =>
          incoming.get(
            node.id
          ) === 0
      )
      .map(
        (node) =>
          node.id
      );

  /*
   * Cyclic/odd model output:
   * guarantee at least one root.
   */
  if (!roots.length) {
    roots = [
      rawNodes[0].id,
    ];
  }

  /*
   * Calculate graph depth.
   */
  const depth =
    new Map();

  roots.forEach(
    (id) =>
      depth.set(
        id,
        0
      )
  );

  const queue =
    [...roots];

  while (queue.length) {
    const current =
      queue.shift();

    const currentDepth =
      depth.get(
        current
      ) || 0;

    const children =
      outgoing.get(
        current
      ) || [];

    children.forEach(
      (child) => {
        const nextDepth =
          Math.max(
            depth.get(
              child
            ) ?? 0,

            currentDepth + 1
          );

        const changed =
          !depth.has(
            child
          ) ||
          nextDepth >
            depth.get(
              child
            );

        depth.set(
          child,
          nextDepth
        );

        if (changed) {
          queue.push(
            child
          );
        }
      }
    );
  }

  /*
   * Any disconnected nodes are
   * placed into additional layers.
   */
  rawNodes.forEach(
    (node, index) => {
      if (
        !depth.has(
          node.id
        )
      ) {
        depth.set(
          node.id,
          Math.max(
            0,
            index
          )
        );
      }
    }
  );

  /*
   * Group nodes into layers.
   */
  const layers =
    new Map();

  rawNodes.forEach(
    (node) => {
      const layer =
        depth.get(
          node.id
        ) || 0;

      if (
        !layers.has(
          layer
        )
      ) {
        layers.set(
          layer,
          []
        );
      }

      layers
        .get(layer)
        .push(node);
    }
  );

  /*
   * Improve the ordering of nodes
   * within each layer.
   *
   * Nodes connected to similar
   * parents are kept close together.
   */
  layers.forEach(
    (layerNodes) => {
      layerNodes.sort(
        (a, b) => {
          const aConnections =
            outgoing.get(
              a.id
            )?.length || 0;

          const bConnections =
            outgoing.get(
              b.id
            )?.length || 0;

          return (
            bConnections -
            aConnections
          );
        }
      );
    }
  );

  /*
   * Calculate positions.
   *
   * Main direction:
   * top → bottom
   *
   * Branches:
   * left ← center → right
   */
  const positions =
    new Map();

  const verticalSpacing =
    rawNodes.length >= 10
      ? 180
      : 205;

  const horizontalSpacing =
    rawNodes.length >= 10
      ? 260
      : 290;

  Array.from(
    layers.entries()
  )
    .sort(
      ([a], [b]) =>
        a - b
    )
    .forEach(
      ([layer, layerNodes]) => {
        const y =
          Number(layer) *
          verticalSpacing;

        /*
         * Center the layer around x = 0.
         */
        const totalWidth =
          (layerNodes.length -
            1) *
          horizontalSpacing;

        const startX =
          -totalWidth / 2;

        layerNodes.forEach(
          (node, index) => {
            positions.set(
              node.id,
              {
                x:
                  startX +
                  index *
                    horizontalSpacing,

                y,
              }
            );
          }
        );
      }
    );

  /*
   * Convert to React Flow nodes.
   */
  const flowNodes =
    rawNodes.map(
      (node) => ({
        id:
          node.id,

        type:
          "ghostNode",

        position:
          positions.get(
            node.id
          ) || {
            x: 0,
            y: 0,
          },

        data: {
          ...node,

          layoutDirection:
            "vertical",
        },

        draggable: true,
      })
    );

  /*
   * React Flow edges.
   */
  const flowEdges =
    edges.map(
      (edge) => ({
        ...edge,

        type:
          "smoothstep",

        animated:
          true,

        style: {
          stroke:
            "#35dfff",

          strokeWidth:
            1.5,

          filter:
            "drop-shadow(0 0 5px rgba(53,223,255,.55))",
        },

        labelStyle: {
          fill:
            "#bcefff",

          fontSize:
            10,

          fontFamily:
            "Inter, sans-serif",
        },

        labelBgStyle: {
          fill:
            "#061017",

          fillOpacity:
            0.95,

          stroke:
            "#164d5b",

          strokeWidth:
            1,
        },

        labelBgPadding:
          [6, 3],

        markerEnd: {
          type:
            MarkerType.ArrowClosed,

          color:
            "#35dfff",
        },
      })
    );

  return {
    nodes:
      flowNodes,

    edges:
      flowEdges,
  };
}

function GhostNode({
  data,
}) {
  const theme =
    PALETTE[
      data.kind
    ] ||
    PALETTE.default;

  return (
    <div
      className="ghost-flow-node"
      style={{
        "--ghost-accent":
          theme.accent,

        "--ghost-glow":
          theme.glow,
      }}
    >
      {/*
       * Every GHOST brain node has
       * a top input and bottom output.
       *
       * React Flow handles the actual
       * connection geometry.
       */}
      <Handle
        type="target"
        position={
          Position.Top
        }
        className="ghost-flow-handle"
      />

      <div className="ghost-flow-node-kicker">
        {data.kind.toUpperCase()}
      </div>

      <div className="ghost-flow-node-label">
        {data.label}
      </div>

      <Handle
        type="source"
        position={
          Position.Bottom
        }
        className="ghost-flow-handle"
      />
    </div>
  );
}

const nodeTypes = {
  ghostNode:
    GhostNode,
};

function GhostFlowDiagram({
  source,
}) {
  const flow =
    useMemo(
      () =>
        buildBrainLayout(
          parseFlowchart(
            source
          )
        ),

      [source]
    );

  if (
    !flow.nodes.length
  ) {
    return (
      <div className="ghost-diagram-error">
        <div className="ghost-diagram-error-title">
          DIAGRAM DATA UNAVAILABLE
        </div>

        <div className="ghost-diagram-error-text">
          GHOST received a diagram
          request but could not
          identify any visual nodes.
        </div>
      </div>
    );
  }

  return (
    <section className="ghost-flow-card">
      <div className="ghost-flow-header">
        <div>
          <span className="ghost-flow-kicker">
            GHOST VISUAL REASONING
          </span>

          <strong>
            NEURAL FLOW MAP
          </strong>
        </div>

        <span className="ghost-flow-live">
          <i />
          REACT FLOW
        </span>
      </div>

      <div
        className="ghost-flow-canvas"
        style={{
          minHeight:
            flow.nodes.length >= 10
              ? "680px"
              : "600px",
        }}
      >
        <ReactFlowProvider>
          <ReactFlow
            nodes={
              flow.nodes
            }

            edges={
              flow.edges
            }

            nodeTypes={
              nodeTypes
            }

            fitView

            fitViewOptions={{
              padding:
                0.22,

              maxZoom:
                1.15,

              minZoom:
                0.35,
            }}

            minZoom={
              0.25
            }

            maxZoom={
              2
            }

            nodesConnectable={
              false
            }

            nodesDraggable={
              true
            }

            elementsSelectable={
              true
            }

            proOptions={{
              hideAttribution:
                true,
            }}

            onInit={(
              instance
            ) => {
              /*
               * Wait for the fullscreen
               * analysis panel to finish
               * its first layout pass.
               *
               * Then fit the entire brain.
               */
              requestAnimationFrame(
                () => {
                  requestAnimationFrame(
                    () => {
                      instance.fitView(
                        {
                          padding:
                            0.22,

                          maxZoom:
                            1.15,

                          minZoom:
                            0.35,

                          duration:
                            400,
                        }
                      );
                    }
                  );
                }
              );
            }}
          >
            <Background
              gap={
                28
              }

              size={
                1
              }

              color={
                "#10313b"
              }
            />

            <Controls
              showInteractive={
                false
              }
            />

            <MiniMap
              pannable
              zoomable

              nodeColor={(
                node
              ) =>
                PALETTE[
                  node.data
                    ?.kind ||
                    "default"
                ]?.accent ||
                PALETTE
                  .default
                  .accent
              }

              maskColor={
                "rgba(1,8,13,.82)"
              }
            />
          </ReactFlow>
        </ReactFlowProvider>
      </div>
    </section>
  );
}

export default GhostFlowDiagram;