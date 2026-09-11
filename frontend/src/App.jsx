import { useState } from "react";
import ChatWindow from "./components/ChatWindow";
import ChatInput from "./components/ChatInput";

function App() {
  const [message, setMessage] = useState("");
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [documentId, setDocumentId] = useState(null);

  const sendMessage = async () => {
    if (!message.trim() || loading) return;

    const userMessage = message.trim();

    setMessages((prev) => [
      ...prev,
      { role: "user", content: userMessage },
    ]);

    setMessage("");
    setLoading(true);

    try {
      const res = await fetch(
        "http://127.0.0.1:8000/api/chat",
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

      if (!res.ok) {
        const errorText = await res.text();
        throw new Error(errorText || "AI request failed");
      }

      if (!res.body) {
        throw new Error(
          "Streaming is not supported by this response"
        );
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();

      let assistantResponse = "";
      let sourcePages = [];

      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: "",
          pages: [],
        },
      ]);

      while (true) {
        const { value, done } = await reader.read();

        if (done) break;

        const chunk = decoder.decode(value, {
          stream: true,
        });

        // Check for page metadata
        if (chunk.includes("__SOURCES__:")) {
          const sourceMatch = chunk.match(
            /__SOURCES__:([0-9,]+)\n?/
          );

          if (sourceMatch) {
            sourcePages = sourceMatch[1]
              .split(",")
              .map((page) => page.trim())
              .filter(Boolean);

            // Remove the internal metadata from the AI response
            const cleanChunk = chunk.replace(
              /__SOURCES__:[0-9,]+\n?/,
              ""
            );

            assistantResponse += cleanChunk;
          }
        } else {
          assistantResponse += chunk;
        }

        setMessages((prev) => {
          const updated = [...prev];

          updated[updated.length - 1] = {
            role: "assistant",
            content: assistantResponse,
            pages: sourcePages,
          };

          return updated;
        });
      }
    } catch (error) {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: `❌ Error: ${error.message}`,
          pages: [],
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const newChat = () => {
    if (loading) return;

    setMessages([]);
    setMessage("");
    setDocumentId(null);
  };

  return (
    <div style={styles.page}>
      <div style={styles.container}>

        <div style={styles.header}>
          <div>
            <h1 style={styles.title}>
              AI Orchestrator
            </h1>

            <p style={styles.subtitle}>
              Multi-provider AI assistant
            </p>
          </div>

          <button
            onClick={newChat}
            disabled={loading}
            style={{
              ...styles.newChatButton,
              opacity: loading ? 0.5 : 1,
              cursor: loading
                ? "not-allowed"
                : "pointer",
            }}
          >
            + New Chat
          </button>
        </div>

        <ChatWindow
          messages={messages}
          loading={loading}
        />

        <ChatInput
          message={message}
          setMessage={setMessage}
          sendMessage={sendMessage}
          loading={loading}
          setDocumentId={setDocumentId}
        />

        <div style={styles.status}>
          <span style={styles.dot}></span>

          <span>Nemotron</span>

          <span style={styles.separator}>•</span>

          <span>Streaming</span>

          <span style={styles.separator}>•</span>

          <span>Backend connected</span>

          {documentId && (
            <>
              <span style={styles.separator}>
                •
              </span>

              <span>
                📄 Document indexed
              </span>
            </>
          )}
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

  header: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: "20px",
  },

  title: {
    margin: 0,
    fontSize: "32px",
  },

  subtitle: {
    color: "#9ca3af",
    margin: "8px 0 0",
  },

  newChatButton: {
    background: "#1f2937",
    color: "white",
    border: "1px solid #374151",
    borderRadius: "10px",
    padding: "10px 16px",
    fontSize: "14px",
    transition: "0.2s",
  },

  status: {
    marginTop: "16px",
    color: "#9ca3af",
    fontSize: "14px",
    display: "flex",
    alignItems: "center",
    gap: "7px",
  },

  dot: {
    display: "inline-block",
    width: "8px",
    height: "8px",
    background: "#22c55e",
    borderRadius: "50%",
  },

  separator: {
    color: "#4b5563",
  },
};

export default App;