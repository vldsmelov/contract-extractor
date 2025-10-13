from fastapi import FastAPI, UploadFile, File, Body, HTTPException
from fastapi.responses import JSONResponse, PlainTextResponse
from typing import Optional, Dict, Any
import json
from pathlib import Path

from .core.config import CONFIG
from .core.schema import load_schema
from .core.validator import SchemaValidator
from .core.field_settings import FieldSettings
from .services.extractor.pipeline import ExtractionPipeline
from .services.warnings import to_payload
from .services.compare import compare_dicts
from .services.utils import read_text_from_upload, read_json_from_upload
from .services.ollama_client import OllamaClient

APP_DIR = Path(__file__).resolve().parent
SCHEMA_PATH = APP_DIR / "assets" / "schema.json"
SYSTEM_PROMPT_PATH = APP_DIR / "prompts" / "system.txt"
USER_TMPL_PATH = APP_DIR / "prompts" / "user_template.txt"
FIELD_GUIDELINES_PATH = APP_DIR / "prompts" / "field_guidelines.md"
FIELD_PROMPTS_DIR = APP_DIR / "prompts" / "fields"
FIELD_EXTRACTORS_PATH = APP_DIR / "assets" / "field_extractors.json"

raw_schema = load_schema(str(SCHEMA_PATH))
field_settings = FieldSettings(
    str(FIELD_EXTRACTORS_PATH),
    str(FIELD_GUIDELINES_PATH),
    str(FIELD_PROMPTS_DIR),
)
schema = field_settings.apply_to_schema(raw_schema)
validator = SchemaValidator(schema)
pipeline = ExtractionPipeline(
    raw_schema,
    str(SYSTEM_PROMPT_PATH),
    str(USER_TMPL_PATH),
    field_settings,
    str(FIELD_GUIDELINES_PATH),
)
client = OllamaClient()

app = FastAPI(title="Contract Extractor API", version=CONFIG.version)

@app.get("/healthz")
async def healthz():
    return {"status": "ok"}

@app.get("/status")
async def status():
    return {
        "status": "ok",
        "use_llm": CONFIG.use_llm,
        "model": CONFIG.model_name,
        "ollama_host": CONFIG.ollama_host,
        "supported_languages": CONFIG.supported_languages,
    }

@app.get("/config")
async def get_config():
    return CONFIG.model_dump()

@app.get("/schema")
async def get_schema():
    return schema

@app.get("/models")
async def get_models():
    try:
        return await client.list_models()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Ollama error: {e}")

@app.get("/version")
async def version():
    return {"version": CONFIG.version, "app": CONFIG.app_name}

@app.post("/check")
async def check(file: UploadFile = File(None), payload: Optional[Dict[str, Any]] = Body(None)):
    # Accept either multipart file or JSON body {"text": "..."}
    if file is None and not payload:
        raise HTTPException(status_code=400, detail="Provide a text file or JSON body with {'text': '...'}")

    if file is not None:
        text = await read_text_from_upload(file)
    else:
        text = payload.get("text", "") if isinstance(payload, dict) else ""

    if not text.strip():
        raise HTTPException(status_code=400, detail="Empty text")

    data, warns, errors, debug = await pipeline.run(text)

    if errors:
        return JSONResponse(
            status_code=422,
            content={
                "ok": False,
                "data": data,
                "warnings": to_payload(warns),
                "validation_errors": errors,
                "debug": debug,
            },
        )

    return {"ok": True, "data": data, "warnings": to_payload(warns), "debug": debug}

@app.post("/test")
async def test(text_file: UploadFile = File(...), gold_json: UploadFile = File(...)):
    text = await read_text_from_upload(text_file)
    gold = await read_json_from_upload(gold_json)

    data, warns, errors, debug = await pipeline.run(text)

    rows, summary = compare_dicts(gold, data)

    return {
        "ok": True,
        "table": rows,
        "summary": summary,
        "warnings": to_payload(warns),
        **({"validation_errors": errors} if errors else {}),
        "debug": debug,
    }
