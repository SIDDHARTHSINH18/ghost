import MessageBubble from "./MessageBubble";

function ChatWindow({ messages, loading }) {
  return (
    <div
      style={{
        minHeight: "400px",
        maxHeight: "500px",
        overflowY: "auto",
        background: "#171a23",
        border: "1px solid #2a2f3a",
        borderRadius: "16px",
        padding: "25px",
        marginBottom: "15px",
      }}
    >
      {messages.length === 0 && !loading && (
        <p style={{ color: "#6b7280" }}>
          Ask your AI Orchestrator something...
        </p>
      )}

      {messages.map((message, index) => (
        <div key={index}>
          <MessageBubble
            role={message.role}
            content={message.content}
          />

          {message.role === "assistant" &&
            message.pages &&
            message.pages.length > 0 && (
              <div style={styles.sources}>
                📄 Sources:{" "}
                {message.pages.map((page, pageIndex) => (
                  <span key={pageIndex}>
                    Page {page}
                    {pageIndex < message.pages.length - 1
                      ? ", "
                      : ""}
                  </span>
                ))}
              </div>
            )}
        </div>
      ))}

      {loading && (
        <div
          style={{
            color: "#9ca3af",
            marginTop: "10px",
          }}
        >
          AI is thinking...
        </div>
      )}
    </div>
  );
}

const styles = {
  sources: {
    marginTop: "4px",
    marginBottom: "14px",
    marginLeft: "4px",
    color: "#6b7280",
    fontSize: "11px",
    fontStyle: "italic",
  },
};

export default ChatWindow;