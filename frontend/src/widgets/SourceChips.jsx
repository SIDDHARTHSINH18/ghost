import React from "react";

/**
 * SourceChips - Reusable chip component for displaying sources/citations
 * Shows document name and page numbers in a tech-styled chip
 */
export default function SourceChips({ sources = [] }) {
  if (!sources || sources.length === 0) {
    return null;
  }

  return (
    <div className="source-chips source-chips-theme">
      {sources.map((source, index) => {
        const { 
          document = source.source || `Source ${index + 1}`, 
          pages = [] 
        } = source;

        return (
          <span key={index} className="source-chip">
            <span className="source-chip-label">{document}</span>
            {pages && pages.length > 0 && (
              <span className="source-chip-pages">
                P.{pages.join(', ')}
              </span>
            )}
          </span>
        );
      })}
    </div>
  );
}