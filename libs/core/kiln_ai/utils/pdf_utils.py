"""
Utilities for working with PDF files.
"""

import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from pypdf import PdfReader, PdfWriter


@contextmanager
def split_pdf_into_pages(pdf_path: Path) -> Generator[list[Path], None, None]:
    with tempfile.TemporaryDirectory(prefix="kiln_pdf_pages_") as temp_dir:
        try:
            page_paths = []

            with open(pdf_path, "rb") as file:
                pdf_reader = PdfReader(file)

                for page_num in range(len(pdf_reader.pages)):
                    pdf_writer = PdfWriter()
                    pdf_writer.add_page(pdf_reader.pages[page_num])

                    # Create temporary file for this page
                    page_filename = f"page_{page_num + 1}.pdf"
                    page_path = Path(temp_dir) / page_filename

                    with open(page_path, "wb") as page_file:
                        pdf_writer.write(page_file)

                    page_paths.append(page_path)

            yield page_paths

        except Exception as e:
            raise RuntimeError(f"Failed to split PDF {pdf_path}: {e}") from e
