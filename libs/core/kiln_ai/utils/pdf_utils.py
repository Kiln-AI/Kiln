"""
Utilities for working with PDF files.
"""

import asyncio
import tempfile
from concurrent.futures import ProcessPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

import pypdfium2
from pypdf import PdfReader, PdfWriter

# some of these operations are expensive, so we should offload them to threads or processes
# but we cannot spawn an infinite number of threads or processes, so we should use a pool
# of threads or processes that are reused
convert_to_image_semaphore = asyncio.Semaphore(1)


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


def _convert_pdf_to_images_sync(pdf_path: Path, output_dir: Path) -> list[Path]:
    image_paths = []

    # note: doing this in a thread causes a segfault - but this is slow and blocking
    # so we should try to find a better way
    pdf = pypdfium2.PdfDocument(pdf_path)
    try:
        for idx, page in enumerate(pdf):
            # scale=2 is legible for ~A4 pages (research papers, etc.) - lower than this is blurry
            bitmap = page.render(scale=2).to_pil()
            target_path = output_dir / f"img-{pdf_path.name}-{idx}.png"
            bitmap.save(target_path)
            image_paths.append(target_path)

        return image_paths
    finally:
        pdf.close()


async def convert_pdf_to_images(pdf_path: Path, output_dir: Path) -> list[Path]:
    async with convert_to_image_semaphore:
        loop = asyncio.get_running_loop()
        with ProcessPoolExecutor(max_workers=1) as executor:
            result = await loop.run_in_executor(
                executor,
                _convert_pdf_to_images_sync,
                pdf_path,
                output_dir,
            )
            return result
