import os

from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from core.orchestrator import Orchestrator
from core.memory import MemoryService
from core.document_processor import DocumentProcessor
from core.retriever import DocumentRetriever
from core.context_optimizer import ContextOptimizer
from core.document_summarizer import DocumentSummarizer
from providers.openai_compatible import OpenAICompatibleProvider
from api.upload import documents


# ============================================================
# ENVIRONMENT
# ============================================================

load_dotenv()


# ============================================================
# ROUTER
# ============================================================

router = APIRouter(
    prefix="/api",
    tags=["Chat"]
)


# ============================================================
# FRIDAY ORCHESTRATOR
# ============================================================

orchestrator = Orchestrator()


# ============================================================
# MEMORY SERVICE
# ============================================================

memory_service = MemoryService()


# ============================================================
# DOCUMENT PROCESSING
# ============================================================

document_processor = DocumentProcessor(
    chunk_size=1500,
    chunk_overlap=200
)


document_retriever = DocumentRetriever(
    top_k=5
)


context_optimizer = ContextOptimizer(
    max_words=4500
)


# ============================================================
# NVIDIA CONFIGURATION
# ============================================================

nvidia_api_key = os.getenv(
    "NVIDIA_API_KEY"
)


nvidia_base_url = os.getenv(
    "NVIDIA_BASE_URL",
    "https://integrate.api.nvidia.com/v1"
)


nvidia_model = os.getenv(
    "NVIDIA_MODEL",
    "nvidia/nemotron-3.5-lightning-30b-a3b"
)


# ============================================================
# REGISTER NEMOTRON
# ============================================================

orchestrator.register_provider(
    "nemotron",
    OpenAICompatibleProvider(
        name="nemotron",
        base_url=nvidia_base_url,
        api_key=nvidia_api_key
    )
)


# ============================================================
# DOCUMENT SUMMARIZER
# ============================================================

document_summarizer = DocumentSummarizer(
    provider=orchestrator.get_provider("nemotron"),
    model=nvidia_model,
    chunk_batch_size=5
)


# ============================================================
# REQUEST MODEL
# ============================================================

class ChatRequest(BaseModel):

    message: str

    provider: str = "nemotron"

    model: str | None = None

    document_id: str | None = None


# ============================================================
# WHOLE DOCUMENT INTENT DETECTION
# ============================================================

def is_whole_document_request(message: str) -> bool:

    text = " ".join(
        message.lower().strip().split()
    )

    whole_document_phrases = [

        # --------------------------------------------------
        # DIRECT DOCUMENT SUMMARY REQUESTS
        # --------------------------------------------------

        "summarize the document",
        "summarise the document",

        "summarize this document",
        "summarise this document",

        "summarize the pdf",
        "summarise the pdf",

        "summarize this pdf",
        "summarise this pdf",

        "summary of the document",
        "summary of this document",

        "summary of the pdf",
        "summary of this pdf",

        # --------------------------------------------------
        # GENERAL SUMMARY REQUESTS
        # --------------------------------------------------

        "give me a summary",
        "give me the summary",

        "give a summary",

        "overall summary",
        "overall overview",

        "complete summary",
        "full summary",

        "detailed summary",
        "comprehensive summary",

        "summarize everything",
        "summarise everything",

        "summarize the whole document",
        "summarise the whole document",

        "summarize entire document",
        "summarise entire document",

        "summarize the entire document",
        "summarise the entire document",

        # --------------------------------------------------
        # OVERVIEW
        # --------------------------------------------------

        "complete overview",
        "full overview",

        "detailed overview",
        "comprehensive overview",

        "overview of the document",
        "overview of this document",

        "give me an overview of the document",
        "give me an overview of this document",

        # --------------------------------------------------
        # DOCUMENT UNDERSTANDING
        # --------------------------------------------------

        "what is this document about",
        "what does this document contain",

        "explain the document",
        "explain this document",

        "analyze the entire document",
        "analyse the entire document",

        "analyze the whole document",
        "analyse the whole document",

        "analyze this document",
        "analyse this document",

        "cover the entire document",
        "cover the whole document",

        # --------------------------------------------------
        # QUESTION GENERATION
        # --------------------------------------------------

        "generate questions from the document",
        "generate questions based on the document",

        "create questions from the document",
        "create questions based on the document",

        "make questions from the document",
        "make questions based on the document",

        "generate quiz questions",
        "create quiz questions"
    ]

    # --------------------------------------------------
    # DIRECT PHRASE MATCH
    # --------------------------------------------------

    if any(
        phrase in text
        for phrase in whole_document_phrases
    ):
        return True

    # --------------------------------------------------
    # STRONG WHOLE-DOCUMENT COMBINATIONS
    # --------------------------------------------------

    summary_words = [
        "summarize",
        "summarise",
        "summary",
        "overview",
        "analyze",
        "analyse",
        "explain"
    ]

    document_words = [
        "document",
        "pdf",
        "file",
        "whole",
        "entire",
        "everything"
    ]

    has_summary_intent = any(
        word in text
        for word in summary_words
    )

    has_document_scope = any(
        word in text
        for word in document_words
    )

    if has_summary_intent and has_document_scope:
        return True

    return False


# ============================================================
# MEMORY CONTEXT
# ============================================================

def get_memory_context(message: str) -> str:

    try:

        context = memory_service.build_context(
            message,
            limit=5
        )

        if context:
            return context

    except Exception as error:

        print(
            f"Memory retrieval error: {error}"
        )

    return ""


# ============================================================
# SAVE CONVERSATION MEMORY
# ============================================================

def save_conversation_memory(
    user_message,
    assistant_response,
    document_id=None
):
    """
    Save only useful user-provided information.

    We intentionally do not blindly store the assistant's
    response as permanent memory.

    FRIDAY's generated responses can contain:
    - generic AI disclaimers
    - temporary reasoning
    - incorrect assumptions
    - repeated information

    Permanent memory should primarily represent useful
    information coming from the user or important project
    context.
    """

    try:

        user_text = user_message.strip()

        if not user_text:
            return

        lower = user_text.lower()

        # --------------------------------------------------
        # Memory triggers
        # --------------------------------------------------

        memory_triggers = [
            "remember",
            "my name is",
            "my project is",
            "i prefer",
            "i like",
            "i don't like",
            "i dont like",
            "i use",
            "i want",
            "i need",
            "we decided",
            "keep in mind",
            "from now on",
            "going forward",
        ]

        should_remember = any(
            trigger in lower
            for trigger in memory_triggers
        )

        if not should_remember:
            return

        # --------------------------------------------------
        # Determine memory type
        # --------------------------------------------------

        memory_type = "user_fact"

        if "project" in lower:
            memory_type = "project"

        elif (
            "prefer" in lower
            or "like" in lower
        ):
            memory_type = "preference"

        elif "decided" in lower:
            memory_type = "decision"

        # --------------------------------------------------
        # Metadata
        # --------------------------------------------------

        metadata = {}

        if document_id:
            metadata["document_id"] = document_id

        # --------------------------------------------------
        # Save
        # --------------------------------------------------

        memory_service.add_memory(
            content=user_text,
            memory_type=memory_type,
            importance=0.8,
            source="user",
            metadata=metadata
        )

        print(
            "FRIDAY memory saved:"
            f" [{memory_type}] {user_text[:100]}"
        )

    except Exception as error:

        print(
            f"Memory save warning: {error}"
        )


# ============================================================
# CHAT ENDPOINT
# ============================================================

@router.post("/chat")
async def chat(request: ChatRequest):

    # ========================================================
    # VALIDATE MESSAGE
    # ========================================================

    if (
        not request.message
        or not request.message.strip()
    ):

        raise HTTPException(
            status_code=400,
            detail="Message cannot be empty."
        )

    # ========================================================
    # GET PROVIDER
    # ========================================================

    provider = orchestrator.get_provider(
        request.provider
    )

    if provider is None:

        raise HTTPException(
            status_code=404,
            detail=(
                f"Provider '{request.provider}' "
                "is not configured"
            )
        )

    # ========================================================
    # RETRIEVED SOURCE PAGES
    # ========================================================

    retrieved_pages = []

    # ========================================================
    # MEMORY
    # ========================================================

    memory_context = get_memory_context(
        request.message
    )

    if memory_context:

        print(
            "\n"
            "----------------------------------------"
        )

        print(
            "RELEVANT MEMORY FOUND"
        )

        print(
            memory_context
        )

        print(
            "----------------------------------------"
        )

    # ========================================================
    # DOCUMENT MODE
    # ========================================================

    if request.document_id:

        document = documents.get(
            request.document_id
        )

        if document is None:

            raise HTTPException(
                status_code=404,
                detail=(
                    "Document not found. "
                    "Please upload the document again."
                )
            )

        chunks = document["chunks"]

        # ====================================================
        # WHOLE DOCUMENT MODE
        # ====================================================

        if is_whole_document_request(
            request.message
        ):

            print(
                "\n"
                "========================================\n"
                "WHOLE DOCUMENT MODE\n"
                "========================================"
            )

            print(
                f"Document: {document['filename']}"
            )

            print(
                f"Total chunks: {len(chunks)}"
            )

            # ------------------------------------------------
            # Check cached summary
            # ------------------------------------------------

            cached_summary = document.get(
                "document_summary"
            )

            if cached_summary:

                print(
                    "Using cached document summary."
                )

                document_summary = cached_summary

            else:

                print(
                    "Creating complete document summary..."
                )

                try:

                    document_summary = (
                        await document_summarizer
                        .create_document_summary(
                            chunks
                        )
                    )

                except Exception as error:

                    print(
                        "Document summarization error:"
                    )

                    print(
                        error
                    )

                    raise HTTPException(
                        status_code=500,
                        detail=(
                            "Could not create the "
                            f"document summary: {str(error)}"
                        )
                    )

                # --------------------------------------------
                # Cache summary
                # --------------------------------------------

                document[
                    "document_summary"
                ] = document_summary

                print(
                    "Document summary created successfully."
                )

            # ------------------------------------------------
            # Whole document = all pages are sources
            # ------------------------------------------------

            for page in document.get(
                "pages",
                []
            ):

                page_number = page.get(
                    "page"
                )

                if page_number is not None:

                    retrieved_pages.append(
                        page_number
                    )

            retrieved_pages.sort()

            source_instruction = (
                "The information comes from "
                "the complete uploaded document."
            )

            # ------------------------------------------------
            # Memory section
            # ------------------------------------------------

            memory_section = ""

            if memory_context:

                memory_section = (
                    "\n\n"
                    "RELEVANT FRIDAY MEMORY:\n"
                    "--------------------------------\n"
                    f"{memory_context}\n"
                    "--------------------------------\n"
                    "Use this memory only when it is "
                    "relevant to the current request.\n"
                )

            # ------------------------------------------------
            # Build whole-document prompt
            # ------------------------------------------------

            user_content = (

                "You are FRIDAY, the user's personal "
                "AI operating system.\n\n"

                "The user has requested a whole-document "
                "analysis rather than a question about "
                "one specific section.\n\n"

                "Use ONLY the document-level understanding "
                "provided below as the document source "
                "of truth.\n\n"

                "DOCUMENT-LEVEL UNDERSTANDING:\n"
                "--------------------------------\n"

                f"{document_summary}\n"

                "--------------------------------\n\n"

                f"{source_instruction}\n"

                f"{memory_section}\n"

                "IMPORTANT:\n"

                "- Give a clear and detailed answer.\n"

                "- Stay faithful to the document.\n"

                "- Do not invent facts.\n"

                "- Cover the important topics and "
                "relationships in the document.\n"

                "- If the requested information is not "
                "supported by the document understanding, "
                "say so clearly.\n"

                "- If the user asks for questions, create "
                "questions based on different parts of "
                "the document.\n"

                "- Do not mismatch a question heading "
                "with its actual question.\n\n"

                f"USER REQUEST:\n{request.message}"
            )

            print(
                f"Whole-document pages: "
                f"{retrieved_pages}"
            )

        # ====================================================
        # TARGETED QUESTION MODE
        # ====================================================

        else:

            # ------------------------------------------------
            # Retrieve relevant chunks
            # ------------------------------------------------

            relevant_chunks = (
                document_retriever.retrieve(
                    request.message,
                    chunks
                )
            )

            # ------------------------------------------------
            # Optimize context
            # ------------------------------------------------

            optimized_chunks = (
                context_optimizer.optimize(
                    relevant_chunks
                )
            )

            # ------------------------------------------------
            # Build document context
            # ------------------------------------------------

            selected_context = (
                context_optimizer.build_context(
                    optimized_chunks
                )
            )

            if not selected_context:

                selected_context = (
                    "No relevant section of the "
                    "uploaded document was found "
                    "for this question."
                )

            # ------------------------------------------------
            # Collect source pages
            # ------------------------------------------------

            for chunk in optimized_chunks:

                start_page = chunk.get(
                    "start_page"
                )

                end_page = chunk.get(
                    "end_page"
                )

                if start_page is None:

                    start_page = chunk.get(
                        "page"
                    )

                if end_page is None:

                    end_page = start_page

                if (
                    start_page is not None
                    and end_page is not None
                ):

                    for page in range(
                        start_page,
                        end_page + 1
                    ):

                        if page not in retrieved_pages:

                            retrieved_pages.append(
                                page
                            )

            retrieved_pages.sort()

            # ------------------------------------------------
            # Source instruction
            # ------------------------------------------------

            if retrieved_pages:

                page_text = ", ".join(
                    str(page)
                    for page in retrieved_pages
                )

                source_instruction = (
                    "The relevant information was "
                    f"found on page(s): {page_text}."
                )

            else:

                source_instruction = (
                    "The page number of the relevant "
                    "information could not be determined."
                )

            # ------------------------------------------------
            # Memory section
            # ------------------------------------------------

            memory_section = ""

            if memory_context:

                memory_section = (
                    "\n\n"
                    "RELEVANT FRIDAY MEMORY:\n"
                    "--------------------------------\n"
                    f"{memory_context}\n"
                    "--------------------------------\n"
                    "Use this memory only when it is "
                    "relevant to the current request. "
                    "The uploaded document remains the "
                    "primary source for document facts.\n"
                )

            # ------------------------------------------------
            # Build targeted question prompt
            # ------------------------------------------------

            user_content = (

                "You are FRIDAY, the user's personal "
                "AI operating system.\n\n"

                "Answer the user's question using the "
                "relevant document context provided below.\n\n"

                "RELEVANT DOCUMENT CONTEXT:\n"
                "--------------------------------\n"

                f"{selected_context}\n"

                "--------------------------------\n\n"

                f"{source_instruction}\n"

                f"{memory_section}\n"

                "IMPORTANT:\n"

                "- Give a clear and detailed answer.\n"

                "- Do not invent information.\n"

                "- If the answer cannot be found in the "
                "provided document context, clearly say "
                "that it was not found.\n"

                "- Use the uploaded document as the "
                "primary source of truth for document facts.\n"

                "- Use FRIDAY memory only when it adds "
                "relevant continuity.\n\n"

                f"USER QUESTION:\n{request.message}"
            )

            # ------------------------------------------------
            # Logging
            # ------------------------------------------------

            print(
                f"\n"
                f"Document: {document['filename']} | "
                f"Chunks: {len(chunks)} | "
                f"Retrieved: {len(relevant_chunks)} | "
                f"Optimized: {len(optimized_chunks)} | "
                f"Pages: {retrieved_pages}"
            )

            print(
                f"Sources for frontend: "
                f"{retrieved_pages}"
            )

    # ========================================================
    # NO DOCUMENT MODE
    # ========================================================

    else:

        # ----------------------------------------------------
        # Build memory-aware prompt
        # ----------------------------------------------------

        if memory_context:
             user_content = (

        "You are FRIDAY, the user's personal "
        "AI operating system.\n\n"

        "You are NOT ChatGPT.\n"

        "Do NOT describe yourself as "
        "\"a language model developed by NVIDIA\" "
        "unless the user explicitly asks about "
        "the underlying AI model or provider.\n\n"

        "IMPORTANT MEMORY BEHAVIOR:\n"

        "The relevant long-term memory below contains "
        "facts already known about the user, their projects, "
        "preferences, decisions, and ongoing work.\n\n"

        "- When the user's question can be answered using "
        "the memory, answer directly using that memory.\n"

        "- Do NOT ask the user to repeat information "
        "already present in memory.\n"

        "- Do NOT ask whether the user means a project "
        "that is already established in memory.\n"

        "- Treat explicit user-provided memories as "
        "established context unless the user corrects them.\n"

        "- Do NOT replace known user-specific information "
        "with a generic answer.\n"

        "- Do NOT say \"I assume\", \"could you tell me\", "
        "or \"what project are you referring to?\" when "
        "the answer is already present in memory.\n"

        "- Only ask a clarification question when the "
        "available memory and current conversation genuinely "
        "do not contain enough information to answer.\n\n"

        "EXAMPLE:\n"

        "If memory says the user's project is FRIDAY and "
        "the user asks \"What are we building?\", answer:\n"

        "\"We're building FRIDAY — your personal AI "
        "operating system.\"\n\n"

        "RELEVANT LONG-TERM MEMORY:\n"
        "--------------------------------\n"

        f"{memory_context}\n"

        "--------------------------------\n\n"

        "IMPORTANT MEMORY RULES:\n"

        "- Use relevant memory when answering "
        "the user's request.\n"

        "- Treat explicit user-provided memory "
        "as authoritative unless the user "
        "corrects it.\n"

        "- Never invent memories.\n"

        "- Do not replace user-specific facts "
        "with generic model information.\n"

        "- The current user request has priority.\n\n"

        f"CURRENT USER REQUEST:\n"
        f"{request.message}"
    )

        else:

            user_content = (

                "You are FRIDAY, the user's personal "
                "AI operating system.\n\n"

                "You are NOT ChatGPT.\n"

                "Do NOT describe yourself as "
                "\"a language model developed by NVIDIA\" "
                "unless the user explicitly asks about "
                "the underlying AI model or provider.\n\n"

                "Answer the user's request directly, "
                "clearly, and naturally.\n\n"

                f"CURRENT USER REQUEST:\n"
                f"{request.message}"
            )

    # ========================================================
    # STREAM RESPONSE
    # ========================================================

    async def generate_response():

        response_text = ""

        try:

            # ------------------------------------------------
            # Send source metadata first
            # ------------------------------------------------

            if (
                request.document_id
                and retrieved_pages
            ):

                yield (
                    "__SOURCES__:"
                    f"{','.join(map(str, retrieved_pages))}\n"
                )

            # ------------------------------------------------
            # Generate AI response
            # ------------------------------------------------

            async for chunk in provider.generate_stream(

                messages=[
                    {
                        "role": "user",
                        "content": user_content
                    }
                ],

                model=(
                    request.model
                    or nvidia_model
                ),

                max_tokens=2048,

                temperature=0.0,

                chat_template_kwargs={
                    "enable_thinking": False
                }
            ):

                # ------------------------------------------------
                # Stream to frontend
                # ------------------------------------------------

                yield chunk

                # ------------------------------------------------
                # Save complete response for memory
                # ------------------------------------------------

                if chunk is not None:

                    response_text += str(
                        chunk
                    )

            # ------------------------------------------------
            # Save conversation after successful generation
            # ------------------------------------------------

            if response_text.strip():

                save_conversation_memory(
                    user_message=request.message,
                    assistant_response=response_text,
                    document_id=request.document_id
                )

        except Exception as error:

            print(
                f"Chat generation error: {error}"
            )

            yield (
                "\n\nError generating response: "
                f"{str(error)}"
            )

    # ========================================================
    # RETURN STREAM
    # ========================================================

    return StreamingResponse(
        generate_response(),
        media_type="text/plain"
    )