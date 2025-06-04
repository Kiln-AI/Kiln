import csv
import json
from pathlib import Path

import pytest

from kiln_ai.adapters.extractors.file_utils import (
    get_mime_type,
    load_file_bytes,
    load_file_text,
)


def create_test_pdf(path: str) -> None:
    """
    Creates a minimal valid PDF file at the specified path for testing purposes.
    
    Args:
        path: The file path where the PDF will be created.
    """
    pdf_path = Path(path).expanduser()

    pdf = b"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R
   /MediaBox [0 0 612 792]
   /Contents 4 0 R
   /Resources << /Font << /F1 5 0 R >> >> >>
endobj
4 0 obj
<< /Length 44 >>
stream
BT
/F1 24 Tf
100 700 Td
(Hello, PDF!) Tj
ET
endstream
endobj
5 0 obj
<< /Type /Font
   /Subtype /Type1
   /BaseFont /Helvetica >>
endobj
xref
0 6
0000000000 65535 f 
0000000010 00000 n 
0000000067 00000 n 
0000000126 00000 n 
0000000275 00000 n 
0000000392 00000 n 
trailer
<< /Size 6 /Root 1 0 R >>
startxref
481
%%EOF
"""

    pdf_path.write_bytes(pdf)
    return pdf_path


@pytest.fixture
def test_files(tmp_path):
    """
    Creates a set of test files in a temporary directory for use in file utility tests.
    
    The generated files include plain text, markdown, CSV, JSON, and a minimal PDF file.
    Returns a dictionary mapping file type keys to their respective file paths.
    """
    files = {}

    # Text file
    text_path = tmp_path / "test.txt"
    text_path.write_text("Hello, World!")
    files["text"] = text_path

    # Markdown file
    md_path = tmp_path / "test.md"
    md_path.write_text("# Test Header\n\nTest content")
    files["markdown"] = md_path

    # CSV file
    csv_path = tmp_path / "test.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["header1", "header2"])
        writer.writerow(["value1", "value2"])
    files["csv"] = csv_path

    # JSON file
    json_path = tmp_path / "test.json"
    json_path.write_text(json.dumps({"test": "value"}))
    files["json"] = json_path

    # PDF file
    pdf_path = create_test_pdf(tmp_path / "test.pdf")
    files["pdf"] = pdf_path

    return files


def test_load_file_bytes(test_files):
    """
    Tests that load_file_bytes correctly reads various file types as bytes and validates their content.
    """
    # Test text file
    assert load_file_bytes(str(test_files["text"])) == b"Hello, World!"

    # Test markdown file
    assert (
        load_file_bytes(str(test_files["markdown"])) == b"# Test Header\n\nTest content"
    )

    # Test CSV file
    csv_content = load_file_bytes(str(test_files["csv"]))
    assert b"header1,header2" in csv_content
    assert b"value1,value2" in csv_content

    # Test JSON file
    assert load_file_bytes(str(test_files["json"])) == b'{"test": "value"}'

    # Test PDF file - just verify we can read it and it's not empty
    pdf_content = load_file_bytes(str(test_files["pdf"]))
    assert len(pdf_content) > 0
    assert pdf_content.startswith(b"%PDF-")


def test_load_file_text(test_files):
    """
    Tests that the load_file_text function correctly reads and returns text content from various file types, including plain text, markdown, CSV, and JSON files.
    """
    # Test text file
    assert load_file_text(str(test_files["text"])) == "Hello, World!"

    # Test markdown file
    assert (
        load_file_text(str(test_files["markdown"])) == "# Test Header\n\nTest content"
    )

    # Test CSV file
    csv_content = load_file_text(str(test_files["csv"]))
    assert "header1,header2" in csv_content
    assert "value1,value2" in csv_content

    # Test JSON file
    assert load_file_text(str(test_files["json"])) == '{"test": "value"}'


def test_get_mime_type(test_files):
    """Test mime type detection for different file types."""
    assert get_mime_type(str(test_files["text"])) == "text/plain"
    assert get_mime_type(str(test_files["markdown"])) == "text/markdown"
    assert get_mime_type(str(test_files["csv"])) == "text/csv"
    assert get_mime_type(str(test_files["json"])) == "application/json"
    assert get_mime_type(str(test_files["pdf"])) == "application/pdf"


def test_file_not_found():
    """
    Tests that loading a non-existent file raises FileNotFoundError.
    """
    with pytest.raises(FileNotFoundError):
        load_file_bytes("nonexistent.txt")

    with pytest.raises(FileNotFoundError):
        load_file_text("nonexistent.txt")


def test_get_mime_type_unknown():
    """
    Tests that get_mime_type raises a ValueError for files with unsupported extensions.
    """
    with pytest.raises(ValueError):
        get_mime_type("unknown.some-non-existent-file-type")
