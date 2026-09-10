import { useState } from "react";

function App() {
  const [message, setMessage] = useState("");
  const [response, setResponse] = useState("");
  const [loading, setLoading] = useState(false);

  const sendMessage = async () => {
    if (!message.trim()) return;

    setLoading(true);
    setResponse("");

    try {
      const res = await fetch("http://127.0.0.1:8000/api/chat", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          message: message,
          provider: "nemotron",
          model: null,
        }),
      });

      const data = await res.json();

      if (!res.ok) {
        throw new Error(data.detail || "AI request failed");
      }

      setResponse(data.response);
    } catch (error) {
      setResponse(`❌ Error: ${error.message}`);
    }

    setLoading(false);
  };

  return (
    <div style={styles.page}>
      <div style={styles.container}>
        <h1>AI Orchestrator</h1>

        <p style={styles.subtitle}>
          Multi-provider AI assistant
        </p>

        <div style={styles.chatBox}>
          {response ? (
            <pre style={styles.response}>{response}</pre>
          ) : (
            <p style={styles.placeholder}>
              Ask your AI Orchestrator something...
            </p>
          )}
        </div>

        <div style={styles.inputRow}>
          <input
            type="text"
            placeholder="Type your message..."
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                sendMessage();
              }
            }}
            style={styles.input}
          />

          <button
            onClick={sendMessage}
            disabled={loading}
            style={styles.button}
          >
            {loading ? "..." : "Send"}
          </button>
        </div>

        <div style={styles.status}>
          <span style={styles.dot}></span>
          Backend: http://127.0.0.1:8000
        </div>
      </div>
    </div>
  );
}

const styles = {
  page: {
    minHeight: "100vh",
    background: "#0f1117",
    color: "white",
    display: "flex",
    justifyContent: "center",
    alignItems: "center",
    fontFamily: "Arial, sans-serif",
    padding: "20px",
    boxSizing: "border-box",
  },

  container: {
    width: "100%",
    maxWidth: "900px",
  },

  subtitle: {
    color: "#9ca3af",
    marginBottom: "30px",
  },

  chatBox: {
    minHeight: "400px",
    background: "#171a23",
    border: "1px solid #2a2f3a",
    borderRadius: "16px",
    padding: "25px",
    marginBottom: "15px",
  },

  placeholder: {
    color: "#6b7280",
  },

  response: {
    whiteSpace: "pre-wrap",
    fontFamily: "Arial, sans-serif",
    fontSize: "16px",
  },

  inputRow: {
    display: "flex",
    gap: "10px",
  },

  input: {
    flex: 1,
    padding: "15px",
    borderRadius: "10px",
    border: "1px solid #333",
    background: "#171a23",
    color: "white",
    fontSize: "16px",
    outline: "none",
  },

  button: {
    padding: "15px 25px",
    borderRadius: "10px",
    border: "none",
    background: "#6366f1",
    color: "white",
    fontSize: "16px",
    cursor: "pointer",
  },

  status: {
    marginTop: "20px",
    color: "#9ca3af",
    fontSize: "14px",
  },

  dot: {
    display: "inline-block",
    width: "8px",
    height: "8px",
    background: "#22c55e",
    borderRadius: "50%",
    marginRight: "8px",
  },
};

export default App;