function MessageBubble({ role, content }) {
  const isUser = role === "user";

  return (
    <div
      style={{
        display: "flex",
        justifyContent: isUser ? "flex-end" : "flex-start",
        marginBottom: "12px",
      }}
    >
      <div
        style={{
          maxWidth: "75%",
          padding: "12px 16px",
          borderRadius: "14px",
          background: isUser ? "#6366f1" : "#252936",
          color: "white",
          whiteSpace: "pre-wrap",
          lineHeight: "1.5",
        }}
      >
        {content}
      </div>
    </div>
  );
}

export default MessageBubble;