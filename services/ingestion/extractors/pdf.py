import pdfplumber

from . import ExtractionError


def extract(file_path):
    # pdfplumber.PDF has no is_encrypted attribute to check up front --
    # password-protected/corrupted PDFs simply raise when opened or read,
    # which the except below already converts into an ExtractionError.
    try:
        with pdfplumber.open(file_path) as pdf:
            parts = []
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    parts.append(page_text)
    except Exception as e:
        raise ExtractionError(f"failed to open/parse PDF: {e}") from e

    text = "\n".join(parts)
    if not text.strip():
        # Likely a scanned-image PDF with no text layer.
        raise ExtractionError("no text layer found (possibly a scanned/image-only PDF)")
    return text
