import pdfplumber

from . import ExtractionError


def extract(file_path):
    try:
        with pdfplumber.open(file_path) as pdf:
            if pdf.is_encrypted:
                raise ExtractionError("password-protected PDF")
            parts = []
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    parts.append(page_text)
    except Exception as e:
        if isinstance(e, ExtractionError):
            raise
        raise ExtractionError(f"failed to open/parse PDF: {e}") from e

    text = "\n".join(parts)
    if not text.strip():
        # Likely a scanned-image PDF with no text layer.
        raise ExtractionError("no text layer found (possibly a scanned/image-only PDF)")
    return text
