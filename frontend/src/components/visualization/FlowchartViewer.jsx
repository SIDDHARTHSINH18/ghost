import React, { useEffect, useRef, useState } from "react";
import mermaid from "mermaid";
import { cleanMermaidSource } from "../../utils/helpers";

/**
 * FlowchartViewer - Mermaid diagram rendering component
 * Renders flowcharts, sequence diagrams, and other Mermaid syntax
 */
export default function FlowchartViewer({ source }) {
  const containerRef = useRef(null);
  const [error, setError] = useState("");
  const [svgReady, setSvgReady] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function renderDiagram() {
      if (!containerRef.current) {
        return;
      }

      // Initialize Mermaid if not already done
      if (window.ghostMermaidConfigured !== true) {
        mermaid.initialize({
          startOnLoad: false,
          securityLevel: "strict",
          theme: "dark",
          flowchart: {
            useMaxWidth: true,
            htmlLabels: false,
            curve: "basis",
          },
          themeVariables: {
            background: "transparent",
            primaryColor: "#06141c",
            primaryTextColor: "#d9f7ff",
            primaryBorderColor: "#00e5ff",
            lineColor: "#32d8ff",
            secondaryColor: "#071a17",
            tertiaryColor: "#130b1c",
            clusterBkg: "rgba(3,12,18,0.72)",
            clusterBorder: "#164d5b",
            fontFamily: "Inter, Segoe UI, sans-serif",
            fontSize: "15px",
          },
        });

        window.ghostMermaidConfigured = true;
      }

      setError("");
      setSvgReady(false);

      const cleaned = cleanMermaidSource(source);
      const id = `ghost-mermaid-${Date.now()}-${Math.random()
        .toString(36)
        .slice(2, 8)}`;

      try {
        const result = await mermaid.render(id, cleaned);

        if (cancelled || !containerRef.current) {
          return;
        }

        containerRef.current.innerHTML = result.svg;

        const svg = containerRef.current.querySelector("svg");
        if (svg) {
          svg.removeAttribute("width");
          svg.removeAttribute("height");
          svg.setAttribute("preserveAspectRatio", "xMidYMid meet");
          svg.style.width = "100%";
          svg.style.height = "auto";
          svg.style.maxHeight = "72vh";
        }

        if (typeof result.bindFunctions === "function") {
          result.bindFunctions(containerRef.current);
        }

        setSvgReady(true);
      } catch (renderError) {
        if (cancelled) {
          return;
        }

        console.error("GHOST Mermaid render error:", renderError);
        setError(renderError?.message || "Unable to render diagram.");
      }
    }

    renderDiagram();

    return () => {
      cancelled = true;
    };
  }, [source]);

  if (error) {
    return (
      <div className="ghost-diagram-error">
        <div className="ghost-diagram-icon">⚠️</div>
        <p className="ghost-diagram-message">{error}</p>
      </div>
    );
  }

  return (
    <div className="ghost-diagram-container">
      <div ref={containerRef} className="ghost-diagram-surface" />
    </div>
  );
}