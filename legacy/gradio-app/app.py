import gradio as gr
from orchestrator import ModelOrchestrator


# Create the orchestrator once when the app starts.
orchestrator = ModelOrchestrator()


def get_models():
    """Return the model names configured in models.json."""
    return list(orchestrator.models_by_name.keys())


def process_message(message, chat_history, image, document, selected_model):
    """Process one chat turn and update the Gradio UI."""

    chat_history = chat_history or []
    message = (message or "").strip()

    # Do nothing if the user supplied absolutely nothing.
    if not message and image is None and document is None:
        return chat_history, "", None, None

    try:
        result = orchestrator.route_request(
            user_input=message,
            history=chat_history,
            image=image,
            document=document,
            model_name=selected_model,
        )

        bot_response = result["response"]

    except Exception as exc:
        bot_response = f"⚠️ Error: {exc}"

    # Add the user's message.
    if message:
        chat_history.append(
            {
                "role": "user",
                "content": message,
            }
        )

    # Add the assistant response.
    chat_history.append(
        {
            "role": "assistant",
            "content": bot_response,
        }
    )

    # Clear text and uploaded files after sending.
    return chat_history, "", None, None


# CSS is passed to launch(), which is compatible with Gradio 6.
CSS = """
.gradio-container {
    max-width: 1200px !important;
}

#chatbot {
    border-radius: 12px;
}
"""


with gr.Blocks() as app:

    # ---------------------------------------------------------
    # Header
    # ---------------------------------------------------------
    gr.Markdown(
        """
        # <center>DeepSeek AI Orchestrator</center>

        <center style="font-size:0.8em; color:#888;">
        Free Open-Source Models · Local Setup
        </center>
        """
    )

    # ---------------------------------------------------------
    # Model selector
    # ---------------------------------------------------------
    model_dropdown = gr.Dropdown(
        choices=get_models(),
        value=orchestrator.default_model,
        label="🤖 Model Selector",
        info="Choose a local open-source model",
    )

    # ---------------------------------------------------------
    # Chatbot
    # ---------------------------------------------------------
    chatbot = gr.Chatbot(
        height=600,
        show_label=False,
        elem_id="chatbot",
    )

    # ---------------------------------------------------------
    # Input area
    # ---------------------------------------------------------
    with gr.Row():

        msg = gr.Textbox(
            placeholder="Type a message...",
            scale=4,
            show_label=False,
            container=False,
        )

        with gr.Column(scale=0, min_width=100):

            image_btn = gr.UploadButton(
                "📎 Image",
                file_types=["image"],
                visible=True,
            )

            doc_btn = gr.UploadButton(
                "📄 Document",
                file_types=[".pdf", ".txt"],
                visible=True,
            )

        send_btn = gr.Button(
            "Send",
            scale=1,
            variant="primary",
        )

    # ---------------------------------------------------------
    # Clear button
    # ---------------------------------------------------------
    gr.ClearButton(
        [msg, chatbot, image_btn, doc_btn],
        value="Clear",
    )

    # ---------------------------------------------------------
    # Send button
    # ---------------------------------------------------------
    send_btn.click(
        fn=process_message,
        inputs=[
            msg,
            chatbot,
            image_btn,
            doc_btn,
            model_dropdown,
        ],
        outputs=[
            chatbot,
            msg,
            image_btn,
            doc_btn,
        ],
    )

    # ---------------------------------------------------------
    # Press Enter to send
    # ---------------------------------------------------------
    msg.submit(
        fn=process_message,
        inputs=[
            msg,
            chatbot,
            image_btn,
            doc_btn,
            model_dropdown,
        ],
        outputs=[
            chatbot,
            msg,
            image_btn,
            doc_btn,
        ],
    )


# -------------------------------------------------------------
# Start application
# -------------------------------------------------------------
if __name__ == "__main__":

    app.launch(
        server_name="127.0.0.1",
        server_port=7860,
        debug=True,
        show_error=True,
        css=CSS,
    )