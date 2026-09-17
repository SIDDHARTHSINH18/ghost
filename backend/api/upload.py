import asyncio
import logging

from fastapi import APIRouter, UploadFile, File, HTTPException
from pypdf import PdfReader
from io import BytesIO
from docx import Document
import uuid

from backend.core.config import get_upload_limits
from backend.core.services import (
    document_processor,
    document_retriever,
    documents,
)


logger = logging.getLogger(
    "ghost.upload",
)


router = APIRouter(prefix="/api", tags=["Files"])


# Resource protection (M1): document processing
# (chunking + embedding) is serialized. Concurrency is
# a safety limit, not a document-count limit — uploads
# queue instead of multiplying memory/CPU pressure.
upload_lock = asyncio.Lock()


@router.get("/documents")
async def list_documents():
    """
    List uploaded documents with safe metadata only.

    Never returns document text, chunks, or embeddings.
    """

    items = []

    total_size = 0

    for document_id, document in documents.items():

        size = document.get(
            "size",
            0,
        )

        total_size += size

        items.append({
            "document_id": document_id,
            "filename": document.get("filename"),
            "content_type": document.get("content_type"),
            "size": size,
            "characters": len(
                document.get("text", ""),
            ),
            "pages": len(
                document.get("pages", []),
            ),
            "chunks": len(
                document.get("chunks", []),
            ),
            "has_summary": bool(
                document.get("document_summary"),
            ),
            "status": "indexed",
        })

    return {
        "documents": items,
        "total": len(items),
        "total_size_bytes": total_size,
    }


@router.delete("/documents/{document_id}")
async def delete_document(document_id: str):
    """
    Delete one uploaded document (text, pages, chunks,
    embeddings) and verify it is gone from the store.
    """

    if document_id not in documents:

        raise HTTPException(
            status_code=404,
            detail="Document not found.",
        )

    documents.pop(document_id)

    # Verify: the id must no longer resolve in the
    # active document store.
    verified = document_id not in documents

    logger.info(
        "Document deleted id=%s verified=%s",
        document_id,
        verified,
    )

    return {
        "deleted": True,
        "verified": verified,
        "document_id": document_id,
    }


@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):

    limits = get_upload_limits()

    content = await file.read()

    filename = (file.filename or "").lower()

    # ----------------------------------------------------
    # Validation: supported type
    # ----------------------------------------------------

    if not filename.endswith(
        tuple(limits.allowed_extensions),
    ):

        allowed_text = ", ".join(
            limits.allowed_extensions,
        )

        raise HTTPException(
            status_code=400,
            detail=(
                "Unsupported file type. "
                f"Allowed: {allowed_text}."
            ),
        )

    # ----------------------------------------------------
    # Validation: per-file size limit
    # ----------------------------------------------------

    if len(content) > limits.max_upload_bytes:

        raise HTTPException(
            status_code=413,
            detail=(
                "File is too large "
                f"({len(content)} bytes). "
                "Maximum per-file size is "
                f"{limits.max_upload_bytes} bytes "
                "(GHOST_MAX_UPLOAD_MB)."
            ),
        )

    # ----------------------------------------------------
    # Validation: aggregate storage limit
    #
    # Real resource protection — the number of documents
    # is deliberately unlimited.
    # ----------------------------------------------------

    total_size = sum(
        doc.get("size", 0)
        for doc
        in documents.values()
    )

    if (
        total_size + len(content)
        > limits.max_total_storage_bytes
    ):

        raise HTTPException(
            status_code=413,
            detail=(
                "Upload would exceed the total document "
                f"storage limit ({limits.max_total_storage_bytes} "
                "bytes, GHOST_MAX_TOTAL_STORAGE_MB). "
                "Delete some documents and try again."
            ),
        )

    try:

        async with upload_lock:

            if filename.endswith(".pdf"):

                reader = PdfReader(BytesIO(content))

                pages = []

                for page_number, page in enumerate(
                    reader.pages,
                    start=1,
                ):

                    page_text = page.extract_text() or ""

                    pages.append({
                        "page": page_number,
                        "text": page_text,
                    })

                full_text = "\n".join(
                    page["text"]
                    for page in pages
                    if page["text"].strip()
                )

            elif filename.endswith(".docx"):

                document = Document(
                    BytesIO(content),
                )

                full_text = "\n".join(
                    paragraph.text
                    for paragraph in document.paragraphs
                )

                pages = [{
                    "page": 1,
                    "text": full_text,
                }]

            else:  # .txt (extension already validated)

                full_text = content.decode(
                    "utf-8",
                    errors="ignore",
                )

                pages = [{
                    "page": 1,
                    "text": full_text,
                }]

            if not full_text.strip():

                raise HTTPException(
                    status_code=400,
                    detail=(
                        "The uploaded document contains "
                        "no readable text."
                    ),
                )

            chunks = document_processor.chunk_text(
                full_text,
            )

            # Calculate the page range for every chunk
            for chunk in chunks:

                chunk_start = chunk["start_word"]
                chunk_end = chunk["end_word"]

                words_before = 0

                start_page = 1
                end_page = 1

                for page in pages:

                    page_word_count = len(
                        page["text"].split(),
                    )

                    page_start = words_before
                    page_end = (
                        words_before
                        + page_word_count
                    )

                    if (
                        chunk_end > page_start
                        and chunk_start < page_end
                    ):

                        if chunk_start >= page_start:
                            start_page = page["page"]

                        end_page = page["page"]

                    words_before = page_end

                chunk["start_page"] = start_page
                chunk["end_page"] = end_page

                # Keep old page field for compatibility
                chunk["page"] = start_page

            # Create semantic embeddings ONCE during upload
            chunks = document_retriever.create_embeddings(
                chunks,
            )

        document_id = str(uuid.uuid4())

        documents[document_id] = {
            "filename": file.filename,
            "content_type": file.content_type,
            "size": len(content),
            "text": full_text,
            "pages": pages,
            "chunks": chunks,
        }

        return {
            "document_id": document_id,
            "filename": file.filename,
            "content_type": file.content_type,
            "size": len(content),
            "characters": len(full_text),
            "pages": len(pages),
            "chunks": len(chunks),
            "message": "File processed and indexed successfully",
        }

    except HTTPException:
        raise

    except Exception as error:

        logger.exception(
            "Upload processing failed: %s",
            type(error).__name__,
        )

        raise HTTPException(
            status_code=500,
            detail=(
                "Could not process the uploaded file. "
                "Check the server logs for details."
            ),
        )
