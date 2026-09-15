import os
import re

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
# GHOST ORCHESTRATOR
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
    provider=orchestrator.get_provider(
        "nemotron"
    ),
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

# ============================================================
# WHOLE DOCUMENT INTENT DETECTION
# ============================================================

def is_whole_document_request(message: str) -> bool:
    text = " ".join(
        message.lower().strip().split()
    )

    # --------------------------------------------------------
    # Explicit whole-document requests
    # --------------------------------------------------------

    whole_document_phrases = [
        # Direct document summaries
        "summarize the doc",
        "summarise the doc",
        "summary of the doc",
        "summarize this doc",
        "summarise this doc",
        "summary of this doc",
        "give me a summary of the doc",
        "give me a summary of this doc",
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

        # Complete / full summaries
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

        # Whole-document overview
        "complete overview",
        "full overview",
        "detailed overview",
        "comprehensive overview",

        "overview of the document",
        "overview of this document",

        "give me an overview of the document",
        "give me an overview of this document",

        # Explicit whole-document analysis
        "analyze the entire document",
        "analyse the entire document",

        "analyze the whole document",
        "analyse the whole document",

        "cover the entire document",
        "cover the whole document",

        # Explicit document understanding
        "what is this document about",
        "what does this document contain",

        "explain the document",
        "explain this document",

        "explain the entire document",
        "explain the whole document",

        "analyze this document",
        "analyse this document",

        # Question generation
        "generate questions from the document",
        "generate questions based on the document",

        "create questions from the document",
        "create questions based on the document",

        "make questions from the document",
        "make questions based on the document",

        "generate quiz questions",
        "create quiz questions"
    ]

    # --------------------------------------------------------
    # Direct explicit match
    # --------------------------------------------------------

    if any(
        phrase in text
        for phrase in whole_document_phrases
    ):
        return True

    # --------------------------------------------------------
    # Strong whole-document intent
    #
    # IMPORTANT:
    # "explain" is intentionally NOT included here.
    #
    # Example:
    # "Explain the Bhakti movement from the PDF"
    # must use targeted retrieval, not whole-document
    # summarization.
    # --------------------------------------------------------

    summary_words = [
        "summarize",
        "summarise",
        "summary",
        "overview"
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

    if (
        has_summary_intent
        and has_document_scope
    ):
        return True

    return False
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

    if (
        has_summary_intent
        and has_document_scope
    ):
        return True

    return False


# ============================================================
# DOCUMENT QUESTION INTENT ROUTING
# ============================================================

def should_use_document(message: str) -> bool:
    """
    Decide whether an uploaded document should be used for this request.

    IMPORTANT:
    The frontend may keep a document_id selected after upload. That does NOT
    mean every later question is a document question.

    Document mode is enabled for explicit document/page requests and for
    questions that clearly refer to the uploaded file. Project/memory
    questions stay in normal GHOST mode even when a PDF is attached.
    """

    if not message:
        return False

    text = " ".join(
        message.lower().strip().split()
    )

    # ------------------------------------------------------------
    # Exact page requests always use the uploaded document.
    # ------------------------------------------------------------

    if extract_requested_page(message) is not None:
        return True

    # ------------------------------------------------------------
    # Explicit whole-document requests always use the document.
    # ------------------------------------------------------------

    if is_whole_document_request(message):
        return True

    # ------------------------------------------------------------
    # Explicit references to the uploaded document.
    # ------------------------------------------------------------

    document_phrases = [
        "uploaded doc",
        "this doc",
        "the doc",
        "in the doc",
        "from the doc",
        "according to the doc",
        "uploaded document",
        "uploaded pdf",
        "uploaded file",
        "this document",
        "this pdf",
        "this file",
        "the document",
        "the pdf",
        "the file",
        "in the document",
        "in this document",
        "in the pdf",
        "in this pdf",
        "from the document",
        "from this document",
        "from the pdf",
        "from this pdf",
        "according to the document",
        "according to this document",
        "according to the pdf",
        "according to this pdf",
        "according to the uploaded document",
        "according to the uploaded pdf",
    ]

    if any(phrase in text for phrase in document_phrases):
        return True

    # ------------------------------------------------------------
    # Strong document-specific question words.
    # These require document terminology as well, so a generic
    # question like "explain the project" stays out of document mode.
    # ------------------------------------------------------------

    document_words = [
        "document",
        "pdf",
        "file",
        "chapter",
        "section",
        "paragraph",
        "passage",
        "page",
        "pages",
        "table",
        "figure",
        "heading",
        "topic in the pdf",
        "topic in the document",
    ]

    if any(word in text for word in document_words):
        return True

    # ------------------------------------------------------------
    # Project/GHOST questions intentionally remain normal GHOST mode.
    # This is the key fix for the problem where an uploaded history PDF
    # hijacked questions about the GHOST project.
    # ------------------------------------------------------------

    return False


# ============================================================
# EXACT PAGE REQUEST DETECTION
# ============================================================

def extract_requested_page(
    message: str
):
    """
    Detect explicit page requests.

    Examples:

    What is on page 49?
    Tell me about page 49
    What does page 49 say?
    Summarize page 49
    Explain pg 49
    What is on p. 49?

    Returns:
        int page number
        None when no explicit page request exists.
    """

    if not message:
        return None

    text = " ".join(
        message.lower().strip().split()
    )

    patterns = [
        r"\bpage\s*\.?\s*(\d+)\b",
        r"\bpages?\s*\.?\s*(\d+)\b",
        r"\bpg\s*\.?\s*(\d+)\b",
        r"\bp\s*\.\s*(\d+)\b"
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            text
        )

        if match:

            try:
                page_number = int(
                    match.group(1)
                )

                if page_number > 0:
                    return page_number

            except ValueError:
                pass

    return None


# ============================================================
# CHUNK PAGE RANGE
# ============================================================

def get_chunk_page_range(
    chunk
):
    """
    Safely determine the page range covered by a chunk.

    Supports:

    page
    start_page
    end_page
    """

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

    try:

        if start_page is not None:
            start_page = int(
                start_page
            )

        if end_page is not None:
            end_page = int(
                end_page
            )

    except (
        TypeError,
        ValueError
    ):

        return None, None

    return (
        start_page,
        end_page
    )


# ============================================================
# FIND EXACT PAGE CHUNKS
# ============================================================

def find_exact_page_chunks(
    chunks,
    requested_page
):
    """
    Return every chunk whose page range
    contains the requested page.

    This intentionally does NOT use semantic
    similarity.

    Page requests are deterministic.
    """

    exact_chunks = []

    for chunk in chunks:

        start_page, end_page = (
            get_chunk_page_range(
                chunk
            )
        )

        if (
            start_page is None
            or end_page is None
        ):
            continue

        if (
            start_page
            <= requested_page
            <= end_page
        ):
            exact_chunks.append(
                chunk
            )

    return exact_chunks


# ============================================================
# CHECK DOCUMENT PAGE INDEX
# ============================================================

def document_has_page(
    document,
    requested_page
):
    """
    Determine whether the uploaded document
    contains the requested page according to
    its indexed page metadata.
    """

    # --------------------------------------------------
    # Check page metadata
    # --------------------------------------------------

    for page in document.get(
        "pages",
        []
    ):

        page_number = page.get(
            "page"
        )

        try:

            if int(
                page_number
            ) == requested_page:

                return True

        except (
            TypeError,
            ValueError
        ):

            continue

    # --------------------------------------------------
    # Check chunk ranges as fallback
    # --------------------------------------------------

    for chunk in document.get(
        "chunks",
        []
    ):

        start_page, end_page = (
            get_chunk_page_range(
                chunk
            )
        )

        if (
            start_page is not None
            and end_page is not None
            and start_page
            <= requested_page
            <= end_page
        ):
            return True

    return False


# ============================================================
# MEMORY CONTEXT
# ============================================================

def get_memory_context(
    message: str
) -> str:

    try:

        context = (
            memory_service.build_context(
                message,
                limit=5
            )
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
    Save useful user-provided information.

    We intentionally do not blindly store the
    assistant's generated response.
    """

    try:

        user_text = (
            user_message.strip()
        )

        if not user_text:
            return

        # Ignore very short messages.

        if len(user_text) < 8:
            return

        # Ignore generic greetings.

        ignored_messages = {
            "hello",
            "hi",
            "hey",
            "thanks",
            "thank you",
            "ok",
            "okay",
            "cool",
            "great",
            "bye"
        }

        if (
            user_text.lower()
            in ignored_messages
        ):
            return

        lower = user_text.lower()

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
            "going forward"
        ]

        should_remember = any(
            trigger in lower
            for trigger in memory_triggers
        )

        if not should_remember:
            return

        # --------------------------------------------------
        # Never store obvious secrets
        # --------------------------------------------------

        secret_terms = [
            "password",
            "api key",
            "apikey",
            "token",
            "secret",
            "private key",
            "otp",
            "credit card"
        ]

        if any(
            term in lower
            for term in secret_terms
        ):
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

        metadata = {
            "automatic": True,
            "source_type": "conversation"
        }

        if document_id:
            metadata[
                "document_id"
            ] = document_id

        # --------------------------------------------------
        # Save memory
        # --------------------------------------------------

        memory_service.add_memory(
            content=user_text,
            memory_type=memory_type,
            importance=0.8,
            source="user",
            metadata=metadata
        )

    except Exception as error:

        print(
            f"Memory save warning: {error}"
        )


# ============================================================
# CHAT ENDPOINT
# ============================================================

@router.post("/chat")
async def chat(
    request: ChatRequest
):

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

    provider = (
        orchestrator.get_provider(
            request.provider
        )
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
    # SOURCE PAGES
    # ========================================================

    retrieved_pages = []

    # ========================================================
    # MEMORY
    # ========================================================

    memory_context = (
        get_memory_context(
            request.message
        )
    )

    if memory_context:

        print(
            "\n----------------------------------------"
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

    # IMPORTANT: document_id only tells us that a document is selected.
    # It does NOT mean every user message should use that document.
    use_document = (
        bool(request.document_id)
        and should_use_document(request.message)
    )

    if use_document:

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

        chunks = document.get(
            "chunks",
            []
        )

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
                f"Document: "
                f"{document.get('filename', 'Unknown')}"
            )

            print(
                f"Total chunks: "
                f"{len(chunks)}"
            )

            # ------------------------------------------------
            # Check cached summary
            # ------------------------------------------------

            cached_summary = (
                document.get(
                    "document_summary"
                )
            )

            if cached_summary:

                print(
                    "Using cached document summary."
                )

                document_summary = (
                    cached_summary
                )

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
                            "document summary: "
                            f"{str(error)}"
                        )
                    )

                document[
                    "document_summary"
                ] = document_summary

                print(
                    "Document summary created successfully."
                )

            # ------------------------------------------------
            # Whole document source pages
            # ------------------------------------------------

            for page in document.get(
                "pages",
                []
            ):

                page_number = page.get(
                    "page"
                )

                if page_number is not None:

                    try:

                        page_number = int(
                            page_number
                        )

                        if (
                            page_number
                            not in retrieved_pages
                        ):

                            retrieved_pages.append(
                                page_number
                            )

                    except (
                        TypeError,
                        ValueError
                    ):

                        continue

            retrieved_pages.sort()

            source_instruction = (
                "The information comes from "
                "the complete uploaded document."
            )

            # ------------------------------------------------
            # Memory
            # ------------------------------------------------

            memory_section = ""

            if memory_context:

                memory_section = (
                    "\n\n"
                    "RELEVANT GHOST MEMORY:\n"
                    "--------------------------------\n"
                    f"{memory_context}\n"
                    "--------------------------------\n"
                    "Use this memory only when it is "
                    "relevant to the current request.\n"
                )

            # ------------------------------------------------
            # Prompt
            # ------------------------------------------------

            user_content = (

                "You are GHOST, the user's personal "
                "AI operating system.\n\n"

                "You are analyzing an uploaded document.\n\n"

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
                "- Cover important topics and relationships.\n"
                "- If the requested information is not "
                "supported by the document understanding, "
                "say so clearly.\n"
                "- If the user asks for questions, create "
                "questions based on different parts of "
                "the document.\n"
                "- Do not mismatch question headings "
                "with their actual questions.\n\n"

                f"USER REQUEST:\n"
                f"{request.message}"
            )

            print(
                f"Whole-document pages: "
                f"{retrieved_pages}"
            )

        # ====================================================
        # TARGETED DOCUMENT MODE
        # ====================================================

        else:

            # ------------------------------------------------
            # EXACT PAGE MODE
            # ------------------------------------------------

            requested_page = (
                extract_requested_page(
                    request.message
                )
            )

            if requested_page is not None:

                print(
                    "\n"
                    "========================================\n"
                    "EXACT PAGE MODE\n"
                    "========================================"
                )

                print(
                    f"Requested page: "
                    f"{requested_page}"
                )

                exact_page_chunks = (
                    find_exact_page_chunks(
                        chunks,
                        requested_page
                    )
                )

                page_exists = (
                    document_has_page(
                        document,
                        requested_page
                    )
                )

                # ============================================
                # PAGE NOT FOUND
                # ============================================

                if (
                    not exact_page_chunks
                    or not page_exists
                ):

                    print(
                        f"Page {requested_page} "
                        "not available in indexed document."
                    )

                    retrieved_pages = []

                    user_content = (

                        "You are GHOST, the user's "
                        "personal AI operating system.\n\n"

                        "The user has asked about an exact "
                        "page in an uploaded document.\n\n"

                        f"REQUESTED PAGE: "
                        f"{requested_page}\n\n"

                        "The requested page is NOT available "
                        "in the indexed document context.\n\n"

                        "IMPORTANT:\n"
                        f"- Clearly tell the user that "
                        f"page {requested_page} is not "
                        "available in the uploaded document "
                        "context.\n"
                        "- Do NOT guess what is on the page.\n"
                        "- Do NOT use information from other "
                        "pages to answer the page-specific "
                        "question.\n"
                        "- Do NOT invent document content.\n"
                        "- Do NOT claim that the page exists "
                        "when it cannot be accessed.\n\n"

                        f"USER QUESTION:\n"
                        f"{request.message}"
                    )

                # ============================================
                # PAGE FOUND
                # ============================================

                else:

                    print(
                        f"Exact page chunks found: "
                        f"{len(exact_page_chunks)}"
                    )

                    # ----------------------------------------
                    # Optimize only the requested page
                    # ----------------------------------------

                    optimized_chunks = (
                        context_optimizer.optimize(
                            exact_page_chunks
                        )
                    )

                    # ----------------------------------------
                    # If optimizer removed everything,
                    # fall back to the exact chunks.
                    # ----------------------------------------

                    if not optimized_chunks:

                        optimized_chunks = (
                            exact_page_chunks
                        )

                    selected_context = (
                        context_optimizer.build_context(
                            optimized_chunks
                        )
                    )

                    if not selected_context:

                        selected_context = (
                            "\n\n".join(
                                chunk.get(
                                    "text",
                                    ""
                                )
                                for chunk
                                in exact_page_chunks
                            )
                        )

                    retrieved_pages = [
                        requested_page
                    ]

                    source_instruction = (
                        "The answer must be based ONLY "
                        f"on page {requested_page} "
                        "of the uploaded document."
                    )

                    # ----------------------------------------
                    # Memory
                    # ----------------------------------------

                    memory_section = ""

                    if memory_context:

                        memory_section = (
                            "\n\n"
                            "RELEVANT GHOST MEMORY:\n"
                            "--------------------------------\n"
                            f"{memory_context}\n"
                            "--------------------------------\n"
                            "Use memory only when it is "
                            "relevant to the user's question. "
                            "Do not use memory to replace "
                            "missing page content.\n"
                        )

                    # ----------------------------------------
                    # Exact page prompt
                    # ----------------------------------------

                    user_content = (

                        "You are GHOST, the user's personal "
                        "AI operating system.\n\n"

                        "You are analyzing an uploaded document.\n\n"

                        f"The user explicitly requested "
                        f"information from page "
                        f"{requested_page}.\n\n"

                        "EXACT PAGE CONTEXT:\n"
                        "================================\n"

                        f"{selected_context}\n"

                        "================================\n\n"

                        f"{source_instruction}\n"

                        f"{memory_section}\n"

                        "IMPORTANT:\n"
                        "- Use ONLY the exact page context "
                        "provided above.\n"
                        "- Do not use information from other "
                        "document pages.\n"
                        "- Do not guess or invent missing "
                        "content.\n"
                        "- Answer the user's exact page "
                        "question directly.\n"
                        "- If the requested information is "
                        "not visible in the supplied page "
                        "context, say that it is not available "
                        "in the page context.\n"
                        f"- Treat page {requested_page} as the "
                        "only authoritative document page "
                        "for this request.\n\n"

                        f"USER QUESTION:\n"
                        f"{request.message}"
                    )

                    print(
                        f"Exact page source: "
                        f"[{requested_page}]"
                    )

            # ------------------------------------------------
            # NORMAL SEMANTIC RETRIEVAL
            # ------------------------------------------------

            else:

                relevant_chunks = (
                    document_retriever.retrieve(
                        request.message,
                        chunks
                    )
                )

                optimized_chunks = (
                    context_optimizer.optimize(
                        relevant_chunks
                    )
                )

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

                # --------------------------------------------
                # Collect source pages
                # --------------------------------------------

                for chunk in optimized_chunks:

                    start_page, end_page = (
                        get_chunk_page_range(
                            chunk
                        )
                    )

                    if (
                        start_page is None
                        or end_page is None
                    ):
                        continue

                    for page in range(
                        start_page,
                        end_page + 1
                    ):

                        if (
                            page
                            not in retrieved_pages
                        ):

                            retrieved_pages.append(
                                page
                            )

                retrieved_pages.sort()

                # --------------------------------------------
                # Source instruction
                # --------------------------------------------

                if retrieved_pages:

                    page_text = ", ".join(
                        str(page)
                        for page
                        in retrieved_pages
                    )

                    source_instruction = (
                        "The relevant information was "
                        f"found on page(s): "
                        f"{page_text}."
                    )

                else:

                    source_instruction = (
                        "The page number of the relevant "
                        "information could not be determined."
                    )

                # --------------------------------------------
                # Memory
                # --------------------------------------------

                memory_section = ""

                if memory_context:

                    memory_section = (
                        "\n\n"
                        "RELEVANT GHOST MEMORY:\n"
                        "--------------------------------\n"
                        f"{memory_context}\n"
                        "--------------------------------\n"
                        "Use this memory only when it "
                        "adds relevant continuity. "
                        "The uploaded document remains "
                        "the primary source for document facts.\n"
                    )

                # --------------------------------------------
                # Normal targeted prompt
                # --------------------------------------------

                user_content = (

                    "You are GHOST, the user's personal "
                    "AI operating system.\n\n"

                    "You are analyzing an uploaded document.\n\n"

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
                    "- Use GHOST memory only when it adds "
                    "relevant continuity.\n\n"

                    f"USER QUESTION:\n"
                    f"{request.message}"
                )

                print(
                    f"\n"
                    f"Document: "
                    f"{document.get('filename', 'Unknown')} | "
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

        if memory_context:

            user_content = (

                "You are GHOST, the user's "
                "personal AI operating system.\n\n"

                "Use the relevant long-term memory "
                "below when it helps maintain continuity.\n\n"

                "RELEVANT LONG-TERM MEMORY:\n"
                "--------------------------------\n"

                f"{memory_context}\n"

                "--------------------------------\n\n"

                "IMPORTANT:\n"
                "- Use memory only when relevant.\n"
                "- Do not assume every memory is correct "
                "if it conflicts with the current request.\n"
                "- The current user request has priority.\n\n"

                f"CURRENT USER REQUEST:\n"
                f"{request.message}"
            )

        else:

            user_content = (

                "You are GHOST, the user's personal "
                "AI operating system.\n\n"

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
            # Special deterministic page-not-found response
            # ------------------------------------------------

            requested_page = (
                extract_requested_page(
                    request.message
                )
            )

            page_chunks = []

            if (
                use_document
                and requested_page is not None
            ):

                document_for_page_check = (
                    documents.get(
                        request.document_id
                    )
                )

                if document_for_page_check:

                    page_chunks = (
                        find_exact_page_chunks(
                            document_for_page_check.get(
                                "chunks",
                                []
                            ),
                            requested_page
                        )
                    )

            if (
                use_document
                and requested_page is not None
                and not page_chunks
            ):

                # --------------------------------------------
                # No source pages are sent here.
                # --------------------------------------------

                yield (
                    "GHOST could not access "
                    f"page {requested_page} "
                    "in the uploaded document context.\n\n"
                    "I will not guess or use another page "
                    "to answer a page-specific question."
                )

                return

            # ------------------------------------------------
            # Send source metadata first
            # ------------------------------------------------

            if (
                use_document
                and retrieved_pages
            ):

                yield (
                    "__SOURCES__:"
                    f"{','.join(
                        map(
                            str,
                            retrieved_pages
                        )
                    )}\n"
                )

            # ------------------------------------------------
            # Generate AI response
            # ------------------------------------------------

            async for chunk in (
                provider.generate_stream(
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
                )
            ):

                yield chunk

                if chunk is not None:

                    response_text += str(
                        chunk
                    )

            # ------------------------------------------------
            # Save useful memory
            # ------------------------------------------------

            if response_text.strip():

                save_conversation_memory(
                    user_message=request.message,
                    assistant_response=response_text,
                    document_id=(
                        request.document_id
                        if use_document
                        else None
                    )
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