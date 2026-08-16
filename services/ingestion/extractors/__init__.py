"""Format-specific extractors. Each module exposes extract(file_path) -> str.

Extractors raise ExtractionError on failure (password-protected, corrupted,
no text layer, etc.) rather than returning empty/partial content silently --
main.py catches this and routes to raw/<hash>.json with extraction_status=failed.
"""


class ExtractionError(Exception):
    pass


from . import docx, xlsx, pdf, image  # noqa: E402,F401

EXTRACTORS_BY_EXT = {
    ".docx": docx.extract,
    ".doc": docx.extract,
    ".xlsx": xlsx.extract,
    ".xls": xlsx.extract,
    ".pdf": pdf.extract,
    ".jpg": image.extract,
    ".jpeg": image.extract,
    ".png": image.extract,
}


def get_extractor(file_extension):
    ext = file_extension.lower()
    if ext not in EXTRACTORS_BY_EXT:
        raise ExtractionError(f"unsupported format: {ext}")
    return EXTRACTORS_BY_EXT[ext]
