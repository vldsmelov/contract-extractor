from typing import Tuple, Optional
from fastapi import UploadFile
import json

async def read_text_from_upload(file: UploadFile) -> str:
    content = await file.read()
    try:
        return content.decode("utf-8")
    except Exception:
        return content.decode("cp1251", errors="ignore")

async def read_json_from_upload(file: UploadFile):
    text = await read_text_from_upload(file)
    return json.loads(text)
