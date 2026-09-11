import { useRef, useState } from "react";

function ChatInput({
  message,
  setMessage,
  sendMessage,
  loading,
  setDocumentId,
}) {
  const fileInputRef = useRef(null);
  const [selectedFile, setSelectedFile] = useState(null);
  const [uploading, setUploading] = useState(false);

  const handleFileSelect = async (event) => {
    const file = event.target.files[0];

    if (!file) return;

    setSelectedFile(file);
    setUploading(true);

    const formData = new FormData();
    formData.append("file", file);

    try {
      const response = await fetch(
        "http://127.0.0.1:8000/api/upload",
        {
          method: "POST",
          body: formData,
        }
      );

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(errorText || "Upload failed");
      }

      const data = await response.json();

      setDocumentId(data.document_id);

      console.log("Document indexed:", data);

    } catch (error) {
      console.error(error);

      alert("File upload failed.");

      setSelectedFile(null);
      setDocumentId(null);

    } finally {
      setUploading(false);
    }
  };

  return (
    <div style={styles.wrapper}>

      {selectedFile && (
        <div style={styles.filePreview}>
          📎 {selectedFile.name}
          {uploading
            ? " • Processing..."
            : " • Document indexed"}
        </div>
      )}

      <div style={styles.inputRow}>

        <button
          type="button"
          onClick={() => fileInputRef.current.click()}
          disabled={loading || uploading}
          style={{
            ...styles.attachButton,
            opacity: loading || uploading ? 0.5 : 1,
          }}
        >
          📎
        </button>

        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.doc,.docx,.txt"
          onChange={handleFileSelect}
          style={{ display: "none" }}
        />

        <input
          type="text"
          value={message}
          onChange={(event) =>
            setMessage(event.target.value)
          }
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              sendMessage();
            }
          }}
          placeholder="Ask something about your document..."
          disabled={loading}
          style={styles.input}
        />

        <button
          onClick={sendMessage}
          disabled={loading || !message.trim()}
          style={{
            ...styles.sendButton,
            opacity:
              loading || !message.trim() ? 0.5 : 1,
          }}
        >
          {loading ? "..." : "Send"}
        </button>

      </div>
    </div>
  );
}

const styles = {
  wrapper: {
    width: "100%",
  },

  filePreview: {
    background: "#1f2937",
    border: "1px solid #374151",
    borderRadius: "8px",
    padding: "8px 12px",
    marginBottom: "8px",
    color: "#d1d5db",
    fontSize: "14px",
  },

  inputRow: {
    display: "flex",
    gap: "8px",
    width: "100%",
  },

  attachButton: {
    width: "48px",
    background: "#1f2937",
    color: "white",
    border: "1px solid #374151",
    borderRadius: "10px",
    fontSize: "20px",
    cursor: "pointer",
  },

  input: {
    flex: 1,
    background: "#181b23",
    color: "white",
    border: "1px solid #303642",
    borderRadius: "10px",
    padding: "12px",
    fontSize: "15px",
    outline: "none",
  },

  sendButton: {
    background: "#6366f1",
    color: "white",
    border: "none",
    borderRadius: "10px",
    padding: "0 22px",
    fontSize: "15px",
    cursor: "pointer",
  },
};

export default ChatInput;