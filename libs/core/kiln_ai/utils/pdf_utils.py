"""
Utilities for working with PDF files.
"""

import asyncio
import atexit
import logging
import tempfile
from concurrent.futures import BrokenExecutor, ProcessPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator

import pypdfium2
from pypdf import PdfReader, PdfWriter

logger = logging.getLogger(__name__)

_pdf_conversion_executor: ProcessPoolExecutor | None = None


def _reset_pdf_conversion_executor():
    """Reset the PDF conversion executor, shutting down the old one if it exists."""
    global _pdf_conversion_executor
    if _pdf_conversion_executor is not None:
        try:
            _pdf_conversion_executor.shutdown(wait=False)
        except Exception:
            pass
        _pdf_conversion_executor = None


# Lazy load for speed, singleton so dev-server reloading doesn't recreate the executor
def get_pdf_conversion_executor() -> ProcessPoolExecutor:
    global _pdf_conversion_executor
    if _pdf_conversion_executor is None:
        _pdf_conversion_executor = ProcessPoolExecutor(max_workers=1)
    return _pdf_conversion_executor


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
    loop = asyncio.get_running_loop()
    executor = get_pdf_conversion_executor()
    try:
        result = await loop.run_in_executor(
            executor,
            _convert_pdf_to_images_sync,
            pdf_path,
            output_dir,
        )
        return result
    except (BrokenExecutor, RuntimeError) as e:
        error_msg = str(e).lower()
        if (
            "process pool" in error_msg
            or "child process" in error_msg
            or isinstance(e, BrokenExecutor)
        ):
            logger.warning(
                f"Process pool became unusable, recreating executor. Error: {e}"
            )
            _reset_pdf_conversion_executor()
            executor = get_pdf_conversion_executor()
            result = await loop.run_in_executor(
                executor,
                _convert_pdf_to_images_sync,
                pdf_path,
                output_dir,
            )
            return result
        raise


def _shutdown_pdf_conversion_executor():
    """Shutdown the PDF conversion executor process."""
    global _pdf_conversion_executor
    if _pdf_conversion_executor is not None:
        _pdf_conversion_executor.shutdown(wait=True)
        _pdf_conversion_executor = None


# Register shutdown function to ensure clean executor termination
atexit.register(_shutdown_pdf_conversion_executor)
