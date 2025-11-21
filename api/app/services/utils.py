from io import BytesIO
from fastapi import UploadFile
import json

from docx import Document


def _is_docx(file: UploadFile) -> bool:
    return (
        (file.filename or "").lower().endswith(".docx")
        or file.content_type
        == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )


def _extract_text_from_docx(content: bytes) -> str:
    document = Document(BytesIO(content))
    chunks = [paragraph.text for paragraph in document.paragraphs if paragraph.text]

    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                cell_text = cell.text.strip()
                if cell_text:
                    chunks.append(cell_text)

    return "\n".join(chunks)


async def read_text_from_upload(file: UploadFile) -> str:
    content = await file.read()

    if _is_docx(file):
        try:
            return _extract_text_from_docx(content)
        except Exception:
            # Fallback to decoding as plain text if DOCX parsing fails
            pass

    try:
        return content.decode("utf-8")
    except Exception:
        return content.decode("cp1251", errors="ignore")


async def read_json_from_upload(file: UploadFile):
    text = await read_text_from_upload(file)
    return json.loads(text)
