import openpyxl
from zipfile import BadZipFile

from . import ExtractionError


def extract(file_path):
    try:
        wb = openpyxl.load_workbook(file_path, data_only=True, read_only=True)
    except (BadZipFile, KeyError, ValueError) as e:
        raise ExtractionError(f"corrupted or unreadable spreadsheet: {e}") from e

    parts = []
    for sheet in wb.worksheets:
        parts.append(f"## Sheet: {sheet.title}")
        for row in sheet.iter_rows(values_only=True):
            cells = [str(c) for c in row if c is not None]
            if cells:
                parts.append(" | ".join(cells))

    text = "\n".join(parts)
    if not text.strip():
        raise ExtractionError("no extractable content found in spreadsheet")
    return text
