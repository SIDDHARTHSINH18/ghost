import {
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import ForceGraph2D from "react-force-graph-2d";

import "./App.css";


const API_URL =
  "http://127.0.0.1:8000";


const NODE_COLORS = {
  ghost: "#ffffff",
  document: "#19f58b",
  memory: "#3b82ff",
  project: "#a855f7",
  task: "#f59e0b",
  tool: "#ff6b35",
};


const NODE_LABELS = {
  ghost: "GHOST",
  document: "Documents",
  memory: "Memory",
  project: "Projects",
  task: "Tasks",
  tool: "Tools",
};


function App() {

  const graphRef = useRef(null);

  const [graphData, setGraphData] =
    useState({
      nodes: [],
      links: [],
    });

  const [selectedNode, setSelectedNode] =
    useState(null);

  const [message, setMessage] =
    useState("");

  const [messages, setMessages] =
    useState([]);

  const [loading, setLoading] =
    useState(false);

  const [documentId, setDocumentId] =
    useState(null);

  const [backendOnline, setBackendOnline] =
    useState(false);

  const ghostState = loading ? "THINKING" : "READY";


  // ============================================================
  // LOAD REAL GHOST GRAPH
  // ============================================================

  useEffect(() => {

    loadGraph();

    const interval =
      setInterval(
        loadGraph,
        5000
      );

    return () =>
      clearInterval(interval);

  }, []);


  async function loadGraph() {

    try {

      const response =
        await fetch(
          `${API_URL}/api/graph`
        );

      if (!response.ok) {
        throw new Error(
          "Graph request failed"
        );
      }

      const data =
        await response.json();

      if (!data.success) {
        throw new Error(
          "Invalid graph response"
        );
      }

      setBackendOnline(true);

      setGraphData({
        nodes: data.nodes || [],
        links: data.edges || [],
      });

    } catch (error) {

      console.error(
        "GHOST graph error:",
        error
      );

      setBackendOnline(false);
    }
  }


  // ============================================================
  // PREPARE FORCE GRAPH
  // ============================================================

  const visualGraph =
    useMemo(() => {

      if (
        !graphData.nodes ||
        graphData.nodes.length === 0
      ) {
        return {
          nodes: [],
          links: [],
        };
      }

      return {
        nodes: graphData.nodes.map(
          (node) => ({
            ...node,
          })
        ),

        links: graphData.links.map(
          (edge) => ({
            ...edge,
            source: edge.source,
            target: edge.target,
          })
        ),
      };

    }, [graphData]);


  // ============================================================
  // CHAT
  // ============================================================

  const sendMessage = async () => {
  if (!message.trim() || loading) {
    return;
  }

  const userMessage = message.trim();

  // Show user's message immediately
  setMessages((previous) => [
    ...previous,
    {
      role: "user",
      content: userMessage,
    },
  ]);

  setMessage("");
  setLoading(true);

  // Create an empty assistant message immediately
  setMessages((previous) => [
    ...previous,
    {
      role: "assistant",
      content: "",
      pages: [],
    },
  ]);

  try {
    const response = await fetch(
      `${API_URL}/api/chat`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          message: userMessage,
          provider: "nemotron",
          model: null,
          document_id: documentId,
        }),
      }
    );

    if (!response.ok) {
      const errorText = await response.text();

      throw new Error(
        errorText || "GHOST request failed"
      );
    }

    if (!response.body) {
      throw new Error(
        "GHOST returned no response body."
      );
    }

    const reader =
      response.body.getReader();

    const decoder =
      new TextDecoder("utf-8");

    let assistantResponse = "";
    let sourcePages = [];

    while (true) {
      const {
        value,
        done,
      } = await reader.read();

      if (done) {
        break;
      }

      const chunk =
        decoder.decode(
          value,
          {
            stream: true,
          }
        );

      if (!chunk) {
        continue;
      }

      // --------------------------------------------------
      // Extract document source pages
      // --------------------------------------------------

      const sourceMatch =
        chunk.match(
          /__SOURCES__:([0-9,\s]+)/
        );

      if (sourceMatch) {
        sourcePages =
          sourceMatch[1]
            .split(",")
            .map((page) =>
              page.trim()
            )
            .filter(Boolean)
            .map(Number);

        // Remove source metadata
        const cleanChunk =
          chunk.replace(
            /__SOURCES__:[0-9,\s]+\n?/,
            ""
          );

        assistantResponse +=
          cleanChunk;
      } else {
        assistantResponse +=
          chunk;
      }

      // --------------------------------------------------
      // Update the assistant message live
      // --------------------------------------------------

      setMessages((previous) => {
        const updated = [...previous];

        // Find the latest assistant message
        let assistantIndex = -1;

        for (
          let i = updated.length - 1;
          i >= 0;
          i--
        ) {
          if (
            updated[i].role ===
            "assistant"
          ) {
            assistantIndex = i;
            break;
          }
        }

        if (assistantIndex === -1) {
          return updated;
        }

        updated[assistantIndex] = {
          ...updated[assistantIndex],
          content:
            assistantResponse,
          pages:
            sourcePages,
        };

        return updated;
      });
    }

    // Flush any remaining decoder data
    assistantResponse +=
      decoder.decode();

    // Final update
    setMessages((previous) => {
      const updated = [...previous];

      let assistantIndex = -1;

      for (
        let i = updated.length - 1;
        i >= 0;
        i--
      ) {
        if (
          updated[i].role ===
          "assistant"
        ) {
          assistantIndex = i;
          break;
        }
      }

      if (assistantIndex !== -1) {
        updated[assistantIndex] = {
          ...updated[assistantIndex],
          content:
            assistantResponse.trim(),
          pages:
            sourcePages,
        };
      }

      return updated;
    });

    // Refresh the GHOST knowledge graph
    setTimeout(() => {
      loadGraph();
    }, 500);

  } catch (error) {
    console.error(
      "GHOST chat error:",
      error
    );

    setMessages((previous) => {
      const updated = [...previous];

      let assistantIndex = -1;

      for (
        let i = updated.length - 1;
        i >= 0;
        i--
      ) {
        if (
          updated[i].role ===
          "assistant"
        ) {
          assistantIndex = i;
          break;
        }
      }

      if (assistantIndex !== -1) {
        updated[assistantIndex] = {
          ...updated[assistantIndex],
          content:
            `GHOST ERROR: ${error.message}`,
          pages: [],
        };
      }

      return updated;
    });

  } finally {
    setLoading(false);
  }
};

  // ============================================================
  // ENTER KEY
  // ============================================================

  const handleKeyDown =
    (event) => {

      if (
        event.key === "Enter" &&
        !event.shiftKey
      ) {

        event.preventDefault();

        sendMessage();
      }
    };


  // ============================================================
  // NODE CLICK
  // ============================================================

  const handleNodeClick =
    (node) => {

      setSelectedNode(node);

    };


  // ============================================================
  // NEW CHAT
  // ============================================================

  const newChat =
    () => {

      if (loading) {
        return;
      }

      setMessages([]);

      setMessage("");

      setDocumentId(null);

      setSelectedNode(null);
    };


  // ============================================================
  // FOCUS GHOST
  // ============================================================

  const focusFriday =
    () => {

      const ghost =
        visualGraph.nodes.find(
          (node) =>
            node.id ===
            "ghost"
        );

      if (
        ghost &&
        graphRef.current
      ) {

        graphRef.current.centerAt(
          ghost.x,
          ghost.y,
          800
        );

        graphRef.current.zoom(
          1.5,
          800
        );
      }
    };


  // ============================================================
  // RENDER
  // ============================================================

  return (

    <div className="ghost-app">

      {/* ======================================================
          TOP LEFT BRAND
      ====================================================== */}

      <div className="brand">

        <div className="brand-title">
          GHOST
        </div>

        <div className="brand-subtitle">
          PERSONAL AI OPERATING SYSTEM
        </div>

      </div>


      {/* ======================================================
          TOP RIGHT STATUS
      ====================================================== */}

      <div className="top-status">

        <span
          className={
            backendOnline
              ? "status-dot online"
              : "status-dot offline"
          }
        />

        <span>
          {backendOnline
            ? "ONLINE"
            : "OFFLINE"}
        </span>

        <span className="status-divider">
          |
        </span>

        <span>
          NEMOTRON
        </span>

      </div>


      {/* ======================================================
          KNOWLEDGE GRAPH
      ====================================================== */}

      <div className={`ghost-core ghost-core-${ghostState.toLowerCase()}`} aria-hidden="true">
        <div className="ghost-core-orbit ghost-core-orbit-a" />
        <div className="ghost-core-orbit ghost-core-orbit-b" />
        <div className="ghost-core-ring">
          <div className="ghost-core-inner">
            <span className="ghost-core-mark">G</span>
            <span className="ghost-core-state">{ghostState}</span>
          </div>
        </div>
        <div className="ghost-core-label">GHOST CORE</div>
      </div>

      <div className="graph-layer">

        {visualGraph.nodes.length > 0 ? (

          <ForceGraph2D

            ref={graphRef}

            graphData={visualGraph}

            backgroundColor="#000000"

            width={window.innerWidth}

            height={window.innerHeight}

            nodeRelSize={4}

            nodeVal={(node) =>
              node.type === "ghost"
                ? 5
                : node.isRoot
                ? 3
                : 1.5
            }

            nodeColor={(node) =>
              NODE_COLORS[
                node.type
              ] || "#ffffff"
            }

            linkColor={() =>
              "rgba(255,255,255,0.10)"
            }

            linkWidth={(link) =>
              link.type === "access"
                ? 1
                : 0.5
            }

            linkDirectionalParticles={
              0
            }

            d3AlphaDecay={1}

            d3VelocityDecay={1}

            cooldownTicks={0}

            enableNodeDrag={true}

            onNodeClick={
              handleNodeClick
            }

            nodeCanvasObject={(
              node,
              ctx,
              globalScale
            ) => {

              const color =
                NODE_COLORS[
                  node.type
                ] || "#ffffff";


              const radius =
                node.type === "ghost"
                  ? 7
                  : node.isRoot
                  ? 5
                  : 3;


              // glow

              ctx.beginPath();

              ctx.arc(
                node.x,
                node.y,
                radius * 2.4,
                0,
                Math.PI * 2
              );

              ctx.fillStyle =
                `${color}22`;

              ctx.fill();


              // node

              ctx.beginPath();

              ctx.arc(
                node.x,
                node.y,
                radius,
                0,
                Math.PI * 2
              );

              ctx.fillStyle =
                color;

              ctx.fill();


              // label

              if (
                globalScale > 0.65
              ) {

                const label =
                  node.label || "";


                ctx.font =
                  `${Math.max(
                    8,
                    10 / globalScale
                  )}px Inter, Arial`;


                ctx.fillStyle =
                  "rgba(255,255,255,0.65)";


                ctx.textAlign =
                  "center";


                ctx.fillText(
                  label,
                  node.x,
                  node.y +
                    radius +
                    13 / globalScale
                );
              }

            }}

          />

        ) : (

          <div className="graph-loading">
            CONNECTING TO GHOST...
          </div>

        )}

      </div>


      {/* ======================================================
          LEFT LEGEND
      ====================================================== */}

      <div className="legend">

        {Object.entries(
          NODE_LABELS
        )
          .filter(
            ([type]) =>
              type !== "ghost"
          )
          .map(
            ([type, label]) => (

              <div
                className="legend-item"
                key={type}
              >

                <span
                  className="legend-dot"
                  style={{
                    background:
                      NODE_COLORS[
                        type
                      ],
                  }}
                />

                <span>
                  {label}
                </span>

              </div>

            )
          )}

      </div>


      {/* ======================================================
          NODE INSPECTOR
      ====================================================== */}

      {selectedNode && (

        <div className="inspector">

          <button
            className="inspector-close"
            onClick={() =>
              setSelectedNode(null)
            }
          >
            ×
          </button>


          <div
            className="inspector-type"
            style={{
              color:
                NODE_COLORS[
                  selectedNode.type
                ],
            }}
          >
            {NODE_LABELS[
              selectedNode.type
            ] || "SYSTEM"}
          </div>


          <div className="inspector-title">
            {selectedNode.label}
          </div>


          <div className="inspector-description">
            {selectedNode.description}
          </div>


          {selectedNode.type ===
            "document" && (

            <div className="inspector-meta">

              <div>
                <span>
                  TYPE
                </span>

                <strong>
                  DOCUMENT
                </strong>
              </div>

              <div>
                <span>
                  CHUNKS
                </span>

                <strong>
                  {
                    selectedNode.chunks ??
                    0
                  }
                </strong>
              </div>

              <div>
                <span>
                  PAGES
                </span>

                <strong>
                  {
                    selectedNode.pages ??
                    0
                  }
                </strong>
              </div>

              <div>
                <span>
                  STATUS
                </span>

                <strong>
                  {
                    selectedNode.status ??
                    "UNKNOWN"
                  }
                </strong>
              </div>

            </div>

          )}


          {selectedNode.type ===
            "tool" && (

            <div className="inspector-status">

              STATUS

              <strong>
                {
                  selectedNode.status ??
                  "UNKNOWN"
                }
              </strong>

            </div>

          )}

        </div>

      )}


      {/* ======================================================
          CHAT RESPONSE OVERLAY
      ====================================================== */}

      {messages.length > 0 && (

        <div className="response-panel">

          <div className="response-header">

            <span>
              GHOST
            </span>

            <button
              onClick={() =>
                setMessages([])
              }
            >
              ×
            </button>

          </div>


          <div className="response-body">

            {messages.map(
              (item, index) => (

                <div
                  className={
                    item.role ===
                    "user"
                      ? "chat-message user"
                      : "chat-message assistant"
                  }
                  key={index}
                >

                  <div className="message-role">

                    {item.role ===
                    "user"
                      ? "YOU"
                      : "GHOST"}

                  </div>

                  <div>
                    {item.content}
                  </div>


                  {item.pages &&
                    item.pages.length >
                      0 && (

                    <div className="source-pages">

                      SOURCES:{" "}

                      {item.pages.join(
                        ", "
                      )}

                    </div>

                  )}

                </div>

              )
            )}

          </div>

        </div>

      )}


      {/* ======================================================
          COMMAND BAR
      ====================================================== */}

      <div className="command-area">

        <div className="ready-label">

          {loading
            ? "GHOST IS THINKING..."
            : "GHOST IS READY"}

        </div>


        <div className="command-bar">

          <button
            className="command-icon"
            onClick={focusFriday}
            title="Center GHOST"
          >
            ◉
          </button>


          <textarea
            value={message}
            onChange={(event) =>
              setMessage(
                event.target.value
              )
            }
            onKeyDown={
              handleKeyDown
            }
            placeholder="Ask GHOST..."
            disabled={loading}
            rows={1}
          />


          <button
            className="send-button"
            onClick={sendMessage}
            disabled={
              loading ||
              !message.trim()
            }
          >
            ↗
          </button>

        </div>


        <div className="command-links">

          <button
            onClick={newChat}
            disabled={loading}
          >
            NEW
          </button>

          <span>|</span>

          <button
            onClick={() =>
              setMessages([])
            }
          >
            CLEAR
          </button>

          <span>|</span>

          <button
            onClick={() =>
              setSelectedNode(
                visualGraph.nodes.find(
                  (node) =>
                    node.id ===
                    "memory-root"
                )
              )
            }
          >
            MEMORY
          </button>

          <span>|</span>

          <button
            onClick={() =>
              setSelectedNode(
                visualGraph.nodes.find(
                  (node) =>
                    node.id ===
                    "project-ghost"
                )
              )
            }
          >
            PROJECTS
          </button>

        </div>

      </div>


      {/* ======================================================
          BOTTOM RIGHT
      ====================================================== */}

      <div className="backend-status">

        <span
          className={
            backendOnline
              ? "status-dot online"
              : "status-dot offline"
          }
        />

        {backendOnline
          ? "BACKEND CONNECTED"
          : "BACKEND OFFLINE"}

      </div>


      {/* ======================================================
          VERSION
      ====================================================== */}

      <div className="version">

        GHOST CORE v0.1

      </div>

    </div>
  );
}


export default App;