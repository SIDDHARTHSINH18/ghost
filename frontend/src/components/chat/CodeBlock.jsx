import { useCallback, useState } from "react";

import {
  highlightSegments,
  normalizeLanguage,
} from "../../utils/codeHighlight";

function CopyButton({ code }) {
  const [copied, setCopied] = useState(false);

  const onCopy = useCallback(() => {
    const write = navigator.clipboard?.writeText(code);

    Promise.resolve(write)
      .then(() => {
        setCopied(true);
        setTimeout(() => setCopied(false), 1600);
      })
      .catch(() => {
        // Clipboard can be unavailable (permissions,
        // insecure context). Fallback keeps copy working.
        const area = document.createElement("textarea");

        area.value = code;
        area.style.position = "fixed";
        area.style.opacity = "0";
        document.body.appendChild(area);
        area.select();

        try {
          document.execCommand("copy");
          setCopied(true);
          setTimeout(() => setCopied(false), 1600);
        } finally {
          document.body.removeChild(area);
        }
      });
  }, [code]);

  return (
    <button
      type="button"
      className="code-copy-btn"
      onClick={onCopy}
      aria-label="Copy code"
    >
      {copied ? "Copied" : "Copy"}
    </button>
  );
}

export default function CodeBlock({ language, code }) {
  const normalized = normalizeLanguage(language);

  const segments = highlightSegments(code, normalized);

  const knownLanguage =
    normalized !== "text" && normalized !== "";

  return (
    <pre className="ghost-code">
      <div className="code-header">
        <span className="code-language-label">
          {knownLanguage ? normalized : "CODE"}
        </span>
        <CopyButton code={code} />
      </div>
      <code>
        {segments.map((segment, index) =>
          segment.className ? (
            <span className={segment.className} key={index}>
              {segment.text}
            </span>
          ) : (
            segment.text
          )
        )}
      </code>
    </pre>
  );
}
