from fastapi import APIRouter, UploadFile, File, HTTPException
from pypdf import PdfReader
from io import BytesIO
from docx import Document
import uuid

from core.document_processor import DocumentProcessor
from core.retriever import DocumentRetriever


router = APIRouter(prefix="/api", tags=["Files"])

documents = {}

document_processor = DocumentProcessor(
    chunk_size=1500,
    chunk_overlap=200
)

document_retriever = DocumentRetriever(
    top_k=5
)


@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):

    content = await file.read()

    filename = file.filename.lower()

    try:

        if filename.endswith(".pdf"):

            reader = PdfReader(BytesIO(content))

            pages = []

            for page_number, page in enumerate(
                reader.pages,
                start=1
            ):

                page_text = page.extract_text() or ""

                pages.append({
                    "page": page_number,
                    "text": page_text
                })

            full_text = "\n".join(
                page["text"]
                for page in pages
                if page["text"].strip()
            )

        elif filename.endswith(".docx"):

            document = Document(
                BytesIO(content)
            )

            full_text = "\n".join(
                paragraph.text
                for paragraph in document.paragraphs
            )

            pages = [{
                "page": 1,
                "text": full_text
            }]

        elif filename.endswith(".txt"):

            full_text = content.decode(
                "utf-8",
                errors="ignore"
            )

            pages = [{
                "page": 1,
                "text": full_text
            }]

        else:

            raise HTTPException(
                status_code=400,
                detail=(
                    "Unsupported file type. "
                    "Use PDF, DOCX, or TXT."
                )
            )

        if not full_text.strip():

            raise HTTPException(
                status_code=400,
                detail="The uploaded document contains no readable text."
            )

        chunks = document_processor.chunk_text(
            full_text
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
                    page["text"].split()
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
        print(
            f"Creating embeddings for {len(chunks)} chunks..."
        )

        chunks = document_retriever.create_embeddings(
            chunks
        )

        print(
            "Embeddings created successfully."
        )

        document_id = str(uuid.uuid4())

        documents[document_id] = {
            "filename": file.filename,
            "content_type": file.content_type,
            "size": len(content),
            "text": full_text,
            "pages": pages,
            "chunks": chunks
        }

        return {
            "document_id": document_id,
            "filename": file.filename,
            "content_type": file.content_type,
            "size": len(content),
            "characters": len(full_text),
            "pages": len(pages),
            "chunks": len(chunks),
            "message": "File processed and indexed successfully"
        }

    except HTTPException:
        raise

    except Exception as error:

        raise HTTPException(
            status_code=500,
            detail=f"Could not process file: {str(error)}"
        )

