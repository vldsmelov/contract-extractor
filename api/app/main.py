from fastapi import FastAPI, UploadFile, File, Body, HTTPException
from fastapi.responses import JSONResponse, PlainTextResponse
from typing import Optional, Dict, Any
import json
from pathlib import Path
import logging

from .core.config import CONFIG
from .core.schema import load_schema
from .core.validator import SchemaValidator
from .core.field_settings import FieldSettings
from .services.extractor.pipeline import ExtractionPipeline
from .services.warnings import to_payload
from .services.compare import compare_dicts
from .services.utils import read_text_from_upload, read_json_from_upload
from .services.ollama_client import OllamaClient, OllamaServiceError

APP_DIR = Path(__file__).resolve().parent
SCHEMA_PATH = APP_DIR / "assets" / "schema.json"
SYSTEM_PROMPT_PATH = APP_DIR / "prompts" / "system.txt"
USER_TMPL_PATH = APP_DIR / "prompts" / "user_template.txt"
FIELD_GUIDELINES_PATH = APP_DIR / "prompts" / "field_guidelines.md"
SUMMARY_SYSTEM_PROMPT_PATH = APP_DIR / "prompts" / "summary_system.txt"
SUMMARY_USER_TMPL_PATH = APP_DIR / "prompts" / "summary_user_template.txt"
FIELD_PROMPTS_DIR = APP_DIR / "prompts" / "fields"
FIELD_EXTRACTORS_PATH = APP_DIR / "assets" / "field_extractors.json"
USER_ASSETS_DIR = APP_DIR / "assets" / "users_assets"
USER_FIELD_EXTRACTORS_PATH = USER_ASSETS_DIR / "field_extractors.json"
FIELD_CONTEXTS_PATH = APP_DIR / "assets" / "field_contexts.json"

raw_schema = load_schema(str(SCHEMA_PATH))
field_settings = FieldSettings(
    str(FIELD_EXTRACTORS_PATH),
    str(FIELD_GUIDELINES_PATH),
    str(FIELD_PROMPTS_DIR),
    str(FIELD_CONTEXTS_PATH),
)
schema = field_settings.apply_to_schema(raw_schema)
validator = SchemaValidator(schema)
pipeline = ExtractionPipeline(
    raw_schema,
    str(SYSTEM_PROMPT_PATH),
    str(USER_TMPL_PATH),
    field_settings,
    str(FIELD_GUIDELINES_PATH),
    str(SUMMARY_SYSTEM_PROMPT_PATH),
    str(SUMMARY_USER_TMPL_PATH),
)
client = OllamaClient()

app = FastAPI(title="Contract Extractor API", version=CONFIG.version)


async def _process_text_payload(text: str):
    try:
        data, warns, errors, debug, ext_prompt = await pipeline.run(text)
    except OllamaServiceError as exc:
        logging.exception("Ollama service error during text processing")
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive safeguard
        logging.exception("Unhandled error during text processing")
        raise HTTPException(status_code=500, detail="Internal processing error") from exc

    response_content = {
        "ext_prompt": ext_prompt or "",
        "data": data,
        "warnings": to_payload(warns),
        "debug": debug,
    }

    if errors:
        response_content.update({"ok": False, "validation_errors": errors})
        return JSONResponse(status_code=422, content=response_content)

    response_content.update({"ok": True})
    return response_content


def _load_json_file(path: Path):
    try:
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Requested resource not found") from exc
    except json.JSONDecodeError as exc:  # pragma: no cover - defensive safeguard
        logging.exception("Invalid JSON content in %s", path)
        raise HTTPException(status_code=500, detail="Invalid JSON content") from exc

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


@app.get("/fields")
async def get_fields(q: str = ""):
    if q == "get":
        return _load_json_file(FIELD_EXTRACTORS_PATH)
    if q == "check":
        return _load_json_file(USER_FIELD_EXTRACTORS_PATH)

    raise HTTPException(status_code=400, detail="Invalid query parameter for 'q'")


@app.post("/change_fields/")
async def change_fields(payload: Dict[str, Any] = Body(...)):
    USER_ASSETS_DIR.mkdir(parents=True, exist_ok=True)

    try:
        with USER_FIELD_EXTRACTORS_PATH.open("w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)
    except TypeError as exc:
        raise HTTPException(status_code=400, detail="Payload is not JSON serializable") from exc

    return {"status": "ok"}


@app.get("/models")
async def get_models():
    try:
        return await client.list_models()
    except OllamaServiceError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
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

    return await _process_text_payload(text)


@app.post("/txtcheck")
async def txtchech(text: str = Body(..., media_type="text/plain")):
    if not text.strip():
        raise HTTPException(status_code=400, detail="Empty text")

    return await _process_text_payload(text)

@app.post("/rawcheck")
async def rawcheck(
    file: UploadFile = File(None), payload: Optional[Dict[str, Any]] = Body(None)
):
    if file is None and not payload:
        raise HTTPException(status_code=400, detail="Provide a text file or JSON body with {'text': '...'}")

    if file is not None:
        text = await read_text_from_upload(file)
    else:
        text = payload.get("text", "") if isinstance(payload, dict) else ""

    if not text.strip():
        raise HTTPException(status_code=400, detail="Empty text")

    _, _, _, debug, _ = await pipeline.run(text)
    raw_outputs = []
    if isinstance(debug, dict):
        raw_outputs = debug.get("llm_raw_outputs") or []

    if not raw_outputs:
        return PlainTextResponse("", status_code=200)

    body = "\n\n-----\n\n".join(raw_outputs)
    return PlainTextResponse(body, status_code=200)

@app.post("/test")
async def test(text_file: UploadFile = File(...), gold_json: UploadFile = File(...)):
    text = await read_text_from_upload(text_file)
    gold = await read_json_from_upload(gold_json)

    data, warns, errors, debug, ext_prompt = await pipeline.run(text)

    rows, summary = compare_dicts(gold, data)

    return {
        "ext_prompt": ext_prompt or "",
        "ok": True,
        "table": rows,
        "summary": summary,
        "warnings": to_payload(warns),
        **({"validation_errors": errors} if errors else {}),
        "debug": debug,
    }
