from pathlib import Path
from unittest.mock import patch

import pytest
from pypdf import PdfReader, PdfWriter

from conftest import MockFileFactoryMimeType
from kiln_ai.utils.pdf_utils import split_pdf_into_pages


def test_split_pdf_into_pages_success(mock_file_factory):
    """Test that split_pdf_into_pages successfully splits a PDF into individual pages."""
    test_file = mock_file_factory(MockFileFactoryMimeType.PDF)

    with split_pdf_into_pages(test_file) as page_paths:
        # Verify we get the expected number of pages (test PDF has 2 pages)
        assert len(page_paths) == 2

        # Verify all page files exist
        for page_path in page_paths:
            assert page_path.exists()
            assert page_path.suffix == ".pdf"

        # Verify page files are named correctly
        assert page_paths[0].name == "page_1.pdf"
        assert page_paths[1].name == "page_2.pdf"

        # Verify each page file is a valid PDF with exactly 1 page
        for page_path in page_paths:
            with open(page_path, "rb") as file:
                reader = PdfReader(file)
                assert len(reader.pages) == 1

    # Verify cleanup: all page files should be removed after context exit
    for page_path in page_paths:
        assert not page_path.exists()


def test_split_pdf_into_pages_file_not_found():
    """Test that split_pdf_into_pages raises RuntimeError for non-existent files."""
    non_existent_file = Path("non_existent.pdf")

    with pytest.raises(RuntimeError, match="Failed to split PDF"):
        with split_pdf_into_pages(non_existent_file):
            pass


def test_split_pdf_into_pages_cleanup_on_exception(mock_file_factory):
    """Test that temporary files are cleaned up even when an exception occurs."""
    test_file = mock_file_factory(MockFileFactoryMimeType.PDF)
    captured_page_paths = []

    def mock_pdf_writer_write(self, stream):
        # Capture the page paths before raising an exception
        captured_page_paths.extend(
            [path for path in test_file.parent.glob("kiln_pdf_pages_*/page_*.pdf")]
        )
        raise Exception("Simulated write error")

    # Patch PdfWriter.write to simulate an error during page writing
    with patch.object(PdfWriter, "write", mock_pdf_writer_write):
        with pytest.raises(RuntimeError, match="Failed to split PDF"):
            with split_pdf_into_pages(test_file):
                pass

    # Verify cleanup happened: no temporary files should remain
    remaining_temp_files = list(test_file.parent.glob("kiln_pdf_pages_*"))
    assert len(remaining_temp_files) == 0


def test_split_pdf_into_pages_empty_pdf(tmp_path):
    """Test handling of an empty or invalid PDF file."""
    # Create an empty file
    empty_pdf = tmp_path / "empty.pdf"
    empty_pdf.write_text("")

    with pytest.raises(RuntimeError, match="Failed to split PDF"):
        with split_pdf_into_pages(empty_pdf):
            pass


def test_split_pdf_into_pages_temporary_directory_creation(mock_file_factory):
    """Test that temporary directories are created with the correct prefix."""
    test_file = mock_file_factory(MockFileFactoryMimeType.PDF)
    captured_temp_dirs = []

    with split_pdf_into_pages(test_file) as page_paths:
        # Check that page paths are in a directory with the expected prefix
        temp_dir = page_paths[0].parent
        captured_temp_dirs.append(temp_dir)
        assert "kiln_pdf_pages_" in temp_dir.name
        assert temp_dir.exists()

    # Verify the temporary directory is cleaned up
    for temp_dir in captured_temp_dirs:
        assert not temp_dir.exists()
