import os

from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from core.orchestrator import Orchestrator
from core.document_processor import DocumentProcessor
from core.retriever import DocumentRetriever
from core.context_optimizer import ContextOptimizer
from core.document_summarizer import DocumentSummarizer
from providers.openai_compatible import OpenAICompatibleProvider
from api.upload import documents


load_dotenv()

router = APIRouter(
    prefix="/api",
    tags=["Chat"]
)


# --------------------------------------------------
# ORCHESTRATOR
# --------------------------------------------------

orchestrator = Orchestrator()


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


# --------------------------------------------------
# NVIDIA CONFIGURATION
# --------------------------------------------------

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


orchestrator.register_provider(
    "nemotron",
    OpenAICompatibleProvider(
        name="nemotron",
        base_url=nvidia_base_url,
        api_key=nvidia_api_key
    )
)


# --------------------------------------------------
# DOCUMENT SUMMARIZER
# --------------------------------------------------

document_summarizer = DocumentSummarizer(
    provider=orchestrator.get_provider("nemotron"),
    model=nvidia_model,
    chunk_batch_size=5
)


# --------------------------------------------------
# REQUEST MODEL
# --------------------------------------------------

class ChatRequest(BaseModel):

    message: str

    provider: str = "nemotron"

    model: str | None = None

    document_id: str | None = None


# --------------------------------------------------
# WHOLE DOCUMENT INTENT DETECTION
# --------------------------------------------------

def is_whole_document_request(message: str) -> bool:

    text = " ".join(
        message.lower().strip().split()
    )

    whole_document_phrases = [

        # Direct document summary requests
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

        # General summary requests
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

        "complete overview",
        "full overview",
        "detailed overview",
        "comprehensive overview",

        "overview of the document",
        "overview of this document",

        "give me an overview of the document",
        "give me an overview of this document",

        # Document understanding
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

    # Direct phrase match
    if any(
        phrase in text
        for phrase in whole_document_phrases
    ):
        return True

    # Strong whole-document combinations
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


# --------------------------------------------------
# CHAT ENDPOINT
# --------------------------------------------------

@router.post("/chat")
async def chat(request: ChatRequest):

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


    retrieved_pages = []


    # ==================================================
    # DOCUMENT MODE
    # ==================================================

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


        # ==================================================
        # WHOLE DOCUMENT MODE
        # ==================================================

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


            # --------------------------------------------------
            # Check whether a summary already exists
            # --------------------------------------------------

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

                    print(error)

                    raise HTTPException(
                        status_code=500,
                        detail=(
                            "Could not create the "
                            f"document summary: {str(error)}"
                        )
                    )


                # Cache summary so future whole-document
                # questions do not repeat the process.

                document[
                    "document_summary"
                ] = document_summary


                print(
                    "Document summary created successfully."
                )


            # --------------------------------------------------
            # Whole document = all pages are sources
            # --------------------------------------------------

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


            # --------------------------------------------------
            # Ask Nemotron to answer using the
            # document-level understanding
            # --------------------------------------------------

            user_content = (

                "You are analyzing an uploaded document.\n\n"

                "The user has requested a whole-document "
                "analysis rather than a question about "
                "one specific section.\n\n"

                "Use ONLY the document-level summary "
                "provided below.\n\n"

                "DOCUMENT-LEVEL UNDERSTANDING:\n"
                "--------------------------------\n"
                f"{document_summary}\n"
                "--------------------------------\n\n"

                f"{source_instruction}\n\n"

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
                "questions that are actually based on "
                "different parts of the document.\n"
                "- Do not mismatch a question heading "
                "with its actual question.\n\n"

                f"USER REQUEST:\n{request.message}"
            )


            print(
                f"Whole-document pages: "
                f"{retrieved_pages}"
            )


        # ==================================================
        # TARGETED QUESTION MODE
        # ==================================================

        else:

            # --------------------------------------------------
            # Retrieve the most relevant chunks
            # --------------------------------------------------

            relevant_chunks = (
                document_retriever.retrieve(
                    request.message,
                    chunks
                )
            )


            # --------------------------------------------------
            # Reduce retrieved context
            # --------------------------------------------------

            optimized_chunks = (
                context_optimizer.optimize(
                    relevant_chunks
                )
            )


            # --------------------------------------------------
            # Build context for AI
            # --------------------------------------------------

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


            # --------------------------------------------------
            # Collect source pages
            # --------------------------------------------------

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


            # Keep sources in numerical order

            retrieved_pages.sort()


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


            # --------------------------------------------------
            # Build targeted-question prompt
            # --------------------------------------------------

            user_content = (

                "You are analyzing an uploaded document.\n\n"

                "Answer the user's question using ONLY "
                "the document context provided below.\n\n"

                "RELEVANT DOCUMENT CONTEXT:\n"
                "--------------------------------\n"
                f"{selected_context}\n"
                "--------------------------------\n\n"

                f"{source_instruction}\n\n"

                "IMPORTANT:\n"
                "- Give a clear and detailed answer.\n"
                "- Do not invent information.\n"
                "- If the answer cannot be found in the "
                "provided context, clearly say that it "
                "was not found.\n"
                "- Use the retrieved document sections "
                "as the primary source of truth.\n\n"

                f"USER QUESTION:\n{request.message}"
            )


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


    # ==================================================
    # NO DOCUMENT MODE
    # ==================================================

    else:

        user_content = request.message


    # ==================================================
    # STREAM RESPONSE
    # ==================================================

    async def generate_response():

        try:

            # --------------------------------------------------
            # Send page metadata to frontend first
            # --------------------------------------------------

            if (
                request.document_id
                and retrieved_pages
            ):

                yield (
                    "__SOURCES__:"
                    f"{','.join(map(str, retrieved_pages))}\n"
                )


            # --------------------------------------------------
            # Generate AI response
            # --------------------------------------------------

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

                yield chunk


        except Exception as error:

            print(
                f"Chat generation error: {error}"
            )

            yield (
                "\n\nError generating response: "
                f"{str(error)}"
            )


    return StreamingResponse(
        generate_response(),
        media_type="text/plain"
    )