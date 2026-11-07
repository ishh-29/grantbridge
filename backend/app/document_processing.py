"""Best-effort text extraction for common nonprofit evidence formats."""
from io import BytesIO
from pathlib import Path

MAX_EXTRACTED_CHARS = 12000


def extract_text(filename: str, content_type: str, data: bytes) -> str:
    suffix = Path(filename).suffix.lower()
    try:
        if content_type == "text/plain" or suffix in {".txt", ".md", ".csv"}:
            text = data.decode("utf-8", errors="replace")
        elif content_type == "application/pdf" or suffix == ".pdf":
            from pypdf import PdfReader
            reader = PdfReader(BytesIO(data), strict=False)
            text = "\n".join((page.extract_text() or "") for page in reader.pages[:40])
        elif suffix == ".docx" or content_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
            from docx import Document as WordDocument
            document = WordDocument(BytesIO(data))
            parts = [paragraph.text for paragraph in document.paragraphs]
            parts.extend(cell.text for table in document.tables for row in table.rows for cell in row.cells)
            text = "\n".join(parts)
        else:
            return ""
    except Exception:
        return ""
    return text[:MAX_EXTRACTED_CHARS].strip()
