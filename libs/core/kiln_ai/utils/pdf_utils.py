"""
Utilities for working with PDF files.
"""

import asyncio
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

from pypdf import PdfReader, PdfWriter


@asynccontextmanager
async def split_pdf_into_pages(pdf_path: Path) -> AsyncGenerator[list[Path], None]:
    with tempfile.TemporaryDirectory(prefix="kiln_pdf_pages_") as temp_dir:
        page_paths = []

        with open(pdf_path, "rb") as file:
            # Reader init can be heavy; offload to thread
            pdf_reader = await asyncio.to_thread(PdfReader, file)

            for page_num in range(len(pdf_reader.pages)):
                await asyncio.sleep(0)
                pdf_writer = PdfWriter()
                pdf_writer.add_page(pdf_reader.pages[page_num])

                # Create temporary file for this page
                page_filename = f"page_{page_num + 1}.pdf"
                page_path = Path(temp_dir) / page_filename

                with open(page_path, "wb") as page_file:
                    # Writing/compression can be expensive; offload to thread
                    await asyncio.to_thread(pdf_writer.write, page_file)

                page_paths.append(page_path)

        yield page_paths
