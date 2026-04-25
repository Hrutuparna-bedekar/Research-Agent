import { useState, useRef } from "react";
import { exportUrl } from "../api";

export function ExportButton({ sessionId, disabled }) {
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  const handleExport = (format) => {
    const url = exportUrl(sessionId, format);
    const a = document.createElement("a");
    a.href = url;
    a.download = `research_${sessionId}.${format === "pdf" ? "pdf" : "md"}`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setOpen(false);
  };

  // Close on outside click
  const handleBlur = () => setTimeout(() => setOpen(false), 150);

  if (disabled) return null;

  return (
    <div className="export-wrapper" ref={ref}>
      <button
        className="export-btn"
        onClick={() => setOpen((o) => !o)}
        onBlur={handleBlur}
      >
        <span>⬇</span>
        Export
        <span style={{ fontSize: "0.7rem", opacity: 0.6 }}>▾</span>
      </button>

      {open && (
        <div className="export-menu">
          <button className="export-option" onClick={() => handleExport("markdown")}>
            <span>📄</span> Markdown (.md)
          </button>
          <button className="export-option" onClick={() => handleExport("pdf")}>
            <span>📋</span> PDF Document
          </button>
        </div>
      )}
    </div>
  );
}
