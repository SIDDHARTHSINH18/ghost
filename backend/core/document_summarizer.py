import asyncio
from typing import List, Dict


class DocumentSummarizer:

    def __init__(
        self,
        provider,
        model,
        chunk_batch_size=5,
        section_size=5,
        max_retries=3
    ):
        self.provider = provider
        self.model = model
        self.chunk_batch_size = chunk_batch_size
        self.section_size = section_size
        self.max_retries = max_retries

    async def _generate_with_retry(
        self,
        messages,
        max_tokens
    ):

        last_error = None

        for attempt in range(1, self.max_retries + 1):

            try:

                return await self.provider.generate(
                    messages=messages,
                    model=self.model,
                    max_tokens=max_tokens,
                    temperature=0.0,
                    chat_template_kwargs={
                        "enable_thinking": False
                    }
                )

            except Exception as error:

                last_error = error

                print(
                    f"AI request failed "
                    f"(attempt {attempt}/"
                    f"{self.max_retries}): {error}"
                )

                if attempt < self.max_retries:

                    await asyncio.sleep(
                        2 ** (attempt - 1)
                    )

        raise last_error

    async def summarize_chunk(
        self,
        text: str
    ) -> str:

        messages = [
            {
                "role": "system",
                "content": (
                    "You are an expert document analysis assistant. "
                    "Summarize the provided document section accurately. "
                    "Preserve important facts, names, dates, concepts, "
                    "arguments, examples, events, causes, effects, "
                    "and relationships. "
                    "Do not invent information. "
                    "Do not omit important information merely to make "
                    "the summary shorter."
                )
            },
            {
                "role": "user",
                "content": (
                    "Summarize this document section.\n\n"
                    + text
                )
            }
        ]

        return await self._generate_with_retry(
            messages,
            max_tokens=1200
        )

    async def _summarize_chunk_worker(
        self,
        index: int,
        chunk: Dict,
        semaphore: asyncio.Semaphore
    ) -> Dict:

        async with semaphore:

            print(
                f"Summarizing chunk "
                f"{index + 1}..."
            )

            summary = await self.summarize_chunk(
                chunk["text"]
            )

            return {
                "chunk_id": chunk["chunk_id"],
                "start_page": chunk.get("start_page"),
                "end_page": chunk.get("end_page"),
                "summary": summary
            }

    async def summarize_chunks(
        self,
        chunks: List[Dict]
    ) -> List[Dict]:

        if not chunks:
            return []

        semaphore = asyncio.Semaphore(
            self.chunk_batch_size
        )

        tasks = [
            self._summarize_chunk_worker(
                index,
                chunk,
                semaphore
            )
            for index, chunk in enumerate(chunks)
        ]

        summaries = await asyncio.gather(
            *tasks
        )

        summaries.sort(
            key=lambda x: x["chunk_id"]
        )

        return summaries

    async def summarize_section(
        self,
        section_summaries: List[Dict]
    ) -> str:

        combined = "\n\n".join(
            (
                f"Chunk {item['chunk_id']} "
                f"(pages {item['start_page']}-"
                f"{item['end_page']}):\n"
                f"{item['summary']}"
            )
            for item in section_summaries
        )

        messages = [
            {
                "role": "system",
                "content": (
                    "You are an expert document synthesis assistant. "
                    "Combine the supplied chunk summaries into one "
                    "accurate section-level summary. "
                    "Preserve important facts, names, dates, "
                    "arguments, concepts, events, examples, "
                    "causes, effects, chronology, and relationships. "
                    "Remove repetition while keeping important details. "
                    "Do not invent information."
                )
            },
            {
                "role": "user",
                "content": (
                    "Create a detailed section summary from these "
                    "chunk summaries:\n\n"
                    + combined
                )
            }
        ]

        return await self._generate_with_retry(
            messages,
            max_tokens=2000
        )

    async def _section_worker(
        self,
        section_number: int,
        section_chunks: List[Dict],
        semaphore: asyncio.Semaphore
    ) -> Dict:

        async with semaphore:

            print(
                f"Creating section summary "
                f"{section_number}..."
            )

            summary = await self.summarize_section(
                section_chunks
            )

            first_chunk = section_chunks[0]
            last_chunk = section_chunks[-1]

            return {
                "section_id": section_number,
                "start_chunk": first_chunk["chunk_id"],
                "end_chunk": last_chunk["chunk_id"],
                "start_page": first_chunk.get(
                    "start_page"
                ),
                "end_page": last_chunk.get(
                    "end_page"
                ),
                "summary": summary
            }

    async def create_section_summaries(
        self,
        chunk_summaries: List[Dict]
    ) -> List[Dict]:

        if not chunk_summaries:
            return []

        section_groups = []

        for start in range(
            0,
            len(chunk_summaries),
            self.section_size
        ):

            section_groups.append(
                chunk_summaries[
                    start:start + self.section_size
                ]
            )

        semaphore = asyncio.Semaphore(
            self.chunk_batch_size
        )

        tasks = [
            self._section_worker(
                index + 1,
                section,
                semaphore
            )
            for index, section in enumerate(
                section_groups
            )
        ]

        sections = await asyncio.gather(
            *tasks
        )

        sections.sort(
            key=lambda x: x["section_id"]
        )

        return sections

    async def create_final_summary(
        self,
        section_summaries: List[Dict]
    ) -> str:

        combined = "\n\n".join(
            (
                f"SECTION {section['section_id']} "
                f"(pages {section['start_page']}-"
                f"{section['end_page']}):\n"
                f"{section['summary']}"
            )
            for section in section_summaries
        )

        messages = [
            {
                "role": "system",
                "content": (
                    "You are an expert document synthesis assistant "
                    "creating a master understanding of an entire "
                    "document.\n\n"
                    "Your job is to preserve balanced coverage of "
                    "EVERY major section of the document.\n\n"
                    "Do not disproportionately focus on the first "
                    "or largest section.\n\n"
                    "Preserve important:\n"
                    "- facts\n"
                    "- names\n"
                    "- dates\n"
                    "- chronology\n"
                    "- concepts\n"
                    "- arguments\n"
                    "- examples\n"
                    "- events\n"
                    "- causes and effects\n"
                    "- historical developments\n"
                    "- relationships between topics\n\n"
                    "Do not invent information.\n"
                    "Do not merge unrelated sections.\n"
                    "Do not omit an entire major section."
                )
            },
            {
                "role": "user",
                "content": (
                    "Create a comprehensive master summary of "
                    "the entire document using the section summaries "
                    "below.\n\n"
                    "Make sure every major section represented below "
                    "receives meaningful coverage.\n\n"
                    + combined
                )
            }
        ]

        return await self._generate_with_retry(
            messages,
            max_tokens=4000
        )

    async def create_document_summary(
        self,
        chunks: List[Dict]
    ) -> str:

        if not chunks:
            return ""

        print(
            "\n===================================="
        )
        print(
            "STARTING HIERARCHICAL SUMMARIZATION"
        )
        print(
            "===================================="
        )

        # ---------------------------------
        # LEVEL 1
        # ---------------------------------

        print(
            f"\nLEVEL 1: Summarizing "
            f"{len(chunks)} chunks..."
        )

        chunk_summaries = await self.summarize_chunks(
            chunks
        )

        print(
            f"LEVEL 1 COMPLETE: "
            f"{len(chunk_summaries)} summaries"
        )

        # ---------------------------------
        # LEVEL 2
        # ---------------------------------

        print(
            "\nLEVEL 2: Creating section summaries..."
        )

        section_summaries = (
            await self.create_section_summaries(
                chunk_summaries
            )
        )

        print(
            f"LEVEL 2 COMPLETE: "
            f"{len(section_summaries)} sections"
        )

        # ---------------------------------
        # LEVEL 3
        # ---------------------------------

        print(
            "\nLEVEL 3: Creating master document summary..."
        )

        final_summary = await self.create_final_summary(
            section_summaries
        )

        print(
            "\n===================================="
        )
        print(
            "HIERARCHICAL SUMMARY COMPLETE"
        )
        print(
            "===================================="
        )

        return final_summary

