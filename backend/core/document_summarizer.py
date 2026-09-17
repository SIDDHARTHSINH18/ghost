import asyncio
from typing import List, Dict


class DocumentSummarizer:

    def __init__(
        self,
        provider,
        model,
        chunk_batch_size=4,
        section_size=6,
        chunks_per_request=2,
        max_retries=2
    ):
        self.provider = provider
        self.model = model

        # Number of AI requests allowed at the same time
        self.chunk_batch_size = chunk_batch_size

        # Number of summarized groups used to build one section
        self.section_size = section_size

        # Number of original document chunks combined into one AI request
        self.chunks_per_request = chunks_per_request

        self.max_retries = max_retries

    # ============================================================
    # AI REQUEST WITH RETRY
    # ============================================================

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

    # ============================================================
    # SINGLE CHUNK SUMMARY
    # ============================================================

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
                    "Do not remove important information merely to "
                    "make the summary shorter."
                )
            },

            {
                "role": "user",
                "content": (
                    "Summarize this document section accurately.\n\n"
                    + text
                )
            }

        ]

        return await self._generate_with_retry(
            messages,
            max_tokens=900
        )

    # ============================================================
    # BATCH CHUNK SUMMARY
    # ============================================================

    async def summarize_chunk_batch(
        self,
        chunks: List[Dict]
    ) -> List[Dict]:

        if not chunks:
            return []

        combined_parts = []

        for chunk in chunks:

            start_page = chunk.get(
                "start_page",
                "?"
            )

            end_page = chunk.get(
                "end_page",
                start_page
            )

            combined_parts.append(
                f"""
DOCUMENT CHUNK {chunk["chunk_id"]}
PAGES {start_page}-{end_page}

{chunk["text"]}
"""
            )

        combined_text = "\n".join(
            combined_parts
        )

        messages = [

            {
                "role": "system",
                "content": (
                    "You are an expert document analysis assistant.\n\n"

                    "You will receive multiple document chunks.\n\n"

                    "Summarize EACH chunk separately.\n\n"

                    "IMPORTANT RULES:\n"
                    "1. Keep the chunks separate.\n"
                    "2. Preserve the chunk number.\n"
                    "3. Preserve important facts, names, dates, "
                    "concepts, arguments, examples, events, causes, "
                    "effects and relationships.\n"
                    "4. Do not invent information.\n"
                    "5. Do not merge unrelated chunks.\n"
                    "6. Do not omit important information.\n\n"

                    "Use exactly this structure:\n\n"

                    "CHUNK <number>\n"
                    "SUMMARY:\n"
                    "<summary>\n\n"

                    "CHUNK <number>\n"
                    "SUMMARY:\n"
                    "<summary>"
                )
            },

            {
                "role": "user",
                "content": (
                    "Create accurate summaries for these "
                    "document chunks:\n\n"
                    + combined_text
                )
            }

        ]

        result = await self._generate_with_retry(
            messages,
            max_tokens=1800
        )

        return self._parse_batch_summaries(
            result,
            chunks
        )

    # ============================================================
    # PARSE BATCH RESULTS
    # ============================================================

    def _parse_batch_summaries(
        self,
        result: str,
        chunks: List[Dict]
    ) -> List[Dict]:

        if not result:
            result = ""

        summaries = []

        for index, chunk in enumerate(chunks):

            chunk_id = chunk["chunk_id"]

            marker = f"CHUNK {chunk_id}"

            start = result.find(marker)

            if start == -1:

                # Fallback to positional marker
                marker = f"CHUNK {index + 1}"
                start = result.find(marker)

            if start == -1:

                summary_text = result.strip()

            else:

                next_positions = []

                for next_chunk in chunks[index + 1:]:

                    next_marker = (
                        f"CHUNK {next_chunk['chunk_id']}"
                    )

                    position = result.find(
                        next_marker,
                        start + len(marker)
                    )

                    if position != -1:
                        next_positions.append(position)

                if next_positions:

                    end = min(next_positions)

                    summary_text = result[
                        start:end
                    ]

                else:

                    summary_text = result[start:]

                if "SUMMARY:" in summary_text:

                    summary_text = summary_text.split(
                        "SUMMARY:",
                        1
                    )[1]

                summary_text = summary_text.strip()

            summaries.append(
                {
                    "chunk_id": chunk_id,
                    "start_page": chunk.get(
                        "start_page"
                    ),
                    "end_page": chunk.get(
                        "end_page"
                    ),
                    "summary": summary_text
                }
            )

        return summaries

    # ============================================================
    # CHUNK BATCH WORKER
    # ============================================================

    async def _chunk_batch_worker(
        self,
        batch_number: int,
        chunks: List[Dict],
        semaphore: asyncio.Semaphore
    ) -> List[Dict]:

        async with semaphore:

            first_id = chunks[0]["chunk_id"]
            last_id = chunks[-1]["chunk_id"]

            print(
                f"Summarizing batch {batch_number} "
                f"(chunks {first_id}-{last_id})..."
            )

            try:

                return await self.summarize_chunk_batch(
                    chunks
                )

            except Exception as error:

                print(
                    f"Batch {batch_number} failed: {error}"
                )

                # Safe fallback:
                # summarize chunks individually
                fallback_results = []

                for chunk in chunks:

                    print(
                        f"Fallback summarizing chunk "
                        f"{chunk['chunk_id']}..."
                    )

                    summary = await self.summarize_chunk(
                        chunk["text"]
                    )

                    fallback_results.append(
                        {
                            "chunk_id": chunk[
                                "chunk_id"
                            ],
                            "start_page": chunk.get(
                                "start_page"
                            ),
                            "end_page": chunk.get(
                                "end_page"
                            ),
                            "summary": summary
                        }
                    )

                return fallback_results

    # ============================================================
    # LEVEL 1
    # ============================================================

    async def summarize_chunks(
        self,
        chunks: List[Dict]
    ) -> List[Dict]:

        if not chunks:
            return []

        # Divide original chunks into small AI batches
        batches = []

        for start in range(
            0,
            len(chunks),
            self.chunks_per_request
        ):

            batches.append(
                chunks[
                    start:
                    start + self.chunks_per_request
                ]
            )

        print(
            f"Created {len(batches)} AI summary batches "
            f"from {len(chunks)} document chunks."
        )

        semaphore = asyncio.Semaphore(
            self.chunk_batch_size
        )

        tasks = [

            self._chunk_batch_worker(
                index + 1,
                batch,
                semaphore
            )

            for index, batch in enumerate(
                batches
            )

        ]

        batch_results = await asyncio.gather(
            *tasks
        )

        summaries = []

        for result in batch_results:
            summaries.extend(result)

        # Preserve document order
        summaries.sort(
            key=lambda x: self._safe_sort_key(
                x["chunk_id"]
            )
        )

        return summaries

    # ============================================================
    # SAFE SORT
    # ============================================================

    @staticmethod
    def _safe_sort_key(value):

        try:
            return (
                0,
                int(value)
            )

        except (
            TypeError,
            ValueError
        ):

            return (
                1,
                str(value)
            )

    # ============================================================
    # LEVEL 2
    # ============================================================

    async def summarize_section(
        self,
        section_summaries: List[Dict]
    ) -> str:

        combined = "\n\n".join(

            (

                f"Chunk {item['chunk_id']} "
                f"(pages "
                f"{item['start_page']}-"
                f"{item['end_page']}):\n"
                f"{item['summary']}"

            )

            for item in section_summaries

        )

        messages = [

            {
                "role": "system",
                "content": (

                    "You are an expert document synthesis assistant.\n\n"

                    "Combine the supplied chunk summaries into "
                    "one accurate section-level summary.\n\n"

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
                    "- relationships\n\n"

                    "Remove repetition while keeping "
                    "important information.\n\n"

                    "Do not invent information."
                )
            },

            {
                "role": "user",
                "content": (

                    "Create a detailed section summary "
                    "from these chunk summaries:\n\n"
                    + combined

                )
            }

        ]

        return await self._generate_with_retry(
            messages,
            max_tokens=1800
        )

    # ============================================================
    # SECTION WORKER
    # ============================================================

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

                "start_chunk": first_chunk[
                    "chunk_id"
                ],

                "end_chunk": last_chunk[
                    "chunk_id"
                ],

                "start_page": first_chunk.get(
                    "start_page"
                ),

                "end_page": last_chunk.get(
                    "end_page"
                ),

                "summary": summary

            }

    # ============================================================
    # CREATE SECTION SUMMARIES
    # ============================================================

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
                    start:
                    start + self.section_size
                ]
            )

        print(
            f"Creating {len(section_groups)} "
            f"section summaries..."
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

    # ============================================================
    # LEVEL 3
    # ============================================================

    async def create_final_summary(
        self,
        section_summaries: List[Dict]
    ) -> str:

        combined = "\n\n".join(

            (

                f"SECTION {section['section_id']} "
                f"(pages "
                f"{section['start_page']}-"
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

                    "Your job is to preserve balanced coverage "
                    "of EVERY major section.\n\n"

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

                    "Create a comprehensive master summary "
                    "of the entire document using the section "
                    "summaries below.\n\n"

                    "Make sure every major section represented "
                    "below receives meaningful coverage.\n\n"

                    + combined

                )
            }

        ]

        return await self._generate_with_retry(
            messages,
            max_tokens=3500
        )

    # ============================================================
    # COMPLETE DOCUMENT SUMMARY
    # ============================================================

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
            "STARTING OPTIMIZED HIERARCHICAL "
            "SUMMARIZATION"
        )

        print(
            "===================================="
        )

        # -----------------------------------------
        # LEVEL 1
        # -----------------------------------------

        print(
            f"\nLEVEL 1: Summarizing "
            f"{len(chunks)} document chunks..."
        )

        print(
            f"Using {self.chunks_per_request} "
            f"chunks per AI request."
        )

        chunk_summaries = await self.summarize_chunks(
            chunks
        )

        print(
            f"LEVEL 1 COMPLETE: "
            f"{len(chunk_summaries)} summaries"
        )

        # -----------------------------------------
        # LEVEL 2
        # -----------------------------------------

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

        # -----------------------------------------
        # LEVEL 3
        # -----------------------------------------

        print(
            "\nLEVEL 3: Creating master "
            "document summary..."
        )

        final_summary = (
            await self.create_final_summary(
                section_summaries
            )
        )

        print(
            "\n===================================="
        )

        print(
            "OPTIMIZED DOCUMENT SUMMARY COMPLETE"
        )

        print(
            "===================================="
        )

        return final_summary