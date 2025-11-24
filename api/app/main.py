import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List

from fastapi import FastAPI, UploadFile, File, Body, HTTPException, Query
from fastapi.responses import JSONResponse

from .core.config import CONFIG
from .core.schema import load_schema
from .core.field_settings import FieldSettings
from .services.extractor.pipeline import ExtractionPipeline
from .services.warnings import to_payload
from .services.utils import read_text_and_sections_from_upload, read_text_from_upload
from .services.ollama_client import OllamaServiceError
from .services.qa import SectionQuestionAnswering

APP_DIR = Path(__file__).resolve().parent
SCHEMA_PATH = APP_DIR / "assets" / "schema.json"
SYSTEM_PROMPT_PATH = APP_DIR / "prompts" / "system.txt"
USER_TMPL_PATH = APP_DIR / "prompts" / "user_template.txt"
FIELD_GUIDELINES_PATH = APP_DIR / "prompts" / "field_guidelines.md"
SUMMARY_SYSTEM_PROMPT_PATH = APP_DIR / "prompts" / "summary_system.txt"
SUMMARY_USER_TMPL_PATH = APP_DIR / "prompts" / "summary_user_template.txt"
QA_SYSTEM_PROMPT_PATH = APP_DIR / "prompts" / "qa_system.txt"
QA_USER_TMPL_PATH = APP_DIR / "prompts" / "qa_user_template.txt"
QA_PLANS_DIR = APP_DIR / "assets" / "qa_plans"
FIELD_PROMPTS_DIR = APP_DIR / "prompts" / "fields"
FIELD_EXTRACTORS_PATH = APP_DIR / "assets" / "field_extractors.json"
FIELD_CONTEXTS_PATH = APP_DIR / "assets" / "field_contexts.json"
USER_ASSETS_DIR = APP_DIR / "assets" / "users_assets"
USER_FIELD_EXTRACTORS_PATH = USER_ASSETS_DIR / "field_extractors.json"
USER_SCHEMA_PATH = USER_ASSETS_DIR / "schema.json"
USER_FIELD_CONTEXTS_PATH = USER_ASSETS_DIR / "contexts.json"
USER_PROMPTS_DIR = APP_DIR / "prompts" / "user_prompts"
USER_FIELD_GUIDELINES_PATH = USER_PROMPTS_DIR / "field_guidelines.md"
USER_SYSTEM_PROMPT_PATH = USER_PROMPTS_DIR / "system.txt"
USER_USER_TMPL_PATH = USER_PROMPTS_DIR / "user_template.txt"
USER_SUMMARY_SYSTEM_PROMPT_PATH = USER_PROMPTS_DIR / "summary_system.txt"
USER_SUMMARY_USER_TMPL_PATH = USER_PROMPTS_DIR / "summary_user_template.txt"
USER_QA_SYSTEM_PROMPT_PATH = USER_PROMPTS_DIR / "qa_system.txt"
USER_QA_USER_TMPL_PATH = USER_PROMPTS_DIR / "qa_user_template.txt"
raw_schema = load_schema(str(SCHEMA_PATH))
field_settings = FieldSettings(
    str(FIELD_EXTRACTORS_PATH),
    str(FIELD_GUIDELINES_PATH),
    str(FIELD_PROMPTS_DIR),
    str(FIELD_CONTEXTS_PATH),
)
pipeline = ExtractionPipeline(
    raw_schema,
    str(SYSTEM_PROMPT_PATH),
    str(USER_TMPL_PATH),
    field_settings,
    str(FIELD_GUIDELINES_PATH),
    str(SUMMARY_SYSTEM_PROMPT_PATH),
    str(SUMMARY_USER_TMPL_PATH),
)
qa_service = (
    SectionQuestionAnswering(str(QA_SYSTEM_PROMPT_PATH), str(QA_USER_TMPL_PATH))
    if CONFIG.use_llm
    else None
)
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


def _load_text_file(path: Path):
    try:
        with path.open("r", encoding="utf-8") as file:
            return file.read()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Requested resource not found") from exc

@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


@app.get("/assets/fields")
async def get_fields(q: str = "", f: str = "extractors"):
    default_files = {
        "extractors": FIELD_EXTRACTORS_PATH,
        "schema": SCHEMA_PATH,
        "contexts": FIELD_CONTEXTS_PATH,
    }
    user_files = {
        "extractors": USER_FIELD_EXTRACTORS_PATH,
        "schema": USER_SCHEMA_PATH,
        "contexts": USER_FIELD_CONTEXTS_PATH,
    }

    if q == "get":
        if f not in default_files:
            raise HTTPException(status_code=400, detail="Invalid query parameter for 'f'")
        return _load_json_file(default_files[f])

    if q == "check":
        if f not in user_files:
            raise HTTPException(status_code=400, detail="Invalid query parameter for 'f'")
        return _load_json_file(user_files[f])

    raise HTTPException(status_code=400, detail="Invalid query parameter for 'q'")


@app.post("/assets/change")
async def change_fields(payload: Dict[str, Any] = Body(...), f: Optional[str] = None):
    user_files = {
        "extractors": USER_FIELD_EXTRACTORS_PATH,
        "schema": USER_SCHEMA_PATH,
        "contexts": USER_FIELD_CONTEXTS_PATH,
    }

    if not f:
        raise HTTPException(status_code=400, detail="Missing query parameter for 'f'")

    if f not in user_files:
        raise HTTPException(status_code=400, detail="Invalid query parameter for 'f'")

    USER_ASSETS_DIR.mkdir(parents=True, exist_ok=True)

    try:
        with user_files[f].open("w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)
    except TypeError as exc:
        raise HTTPException(status_code=400, detail="Payload is not JSON serializable") from exc

    return {"status": "ok"}


@app.get("/prompts/system")
async def get_prompts(q: str = "", f: Optional[List[str]] = Query(None)):
    default_files = {
        "field_guidelines": FIELD_GUIDELINES_PATH,
        "summary_system": SUMMARY_SYSTEM_PROMPT_PATH,
        "summary_user_template": SUMMARY_USER_TMPL_PATH,
        "qa_system": QA_SYSTEM_PROMPT_PATH,
        "qa_user_template": QA_USER_TMPL_PATH,
        "system": SYSTEM_PROMPT_PATH,
        "user_template": USER_TMPL_PATH,
    }

    user_files = {
        "field_guidelines": USER_FIELD_GUIDELINES_PATH,
        "summary_system": USER_SUMMARY_SYSTEM_PROMPT_PATH,
        "summary_user_template": USER_SUMMARY_USER_TMPL_PATH,
        "qa_system": USER_QA_SYSTEM_PROMPT_PATH,
        "qa_user_template": USER_QA_USER_TMPL_PATH,
        "system": USER_SYSTEM_PROMPT_PATH,
        "user_template": USER_USER_TMPL_PATH,
    }

    target_files = None
    if q == "get":
        target_files = default_files
    elif q == "check":
        target_files = user_files
    else:
        raise HTTPException(status_code=400, detail="Invalid query parameter for 'q'")

    keys = f or list(target_files.keys())
    invalid_keys = [key for key in keys if key not in target_files]
    if invalid_keys:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid query parameter for 'f': {', '.join(sorted(set(invalid_keys)))}",
        )

    return {key: _load_text_file(target_files[key]) for key in keys}


@app.post("/prompts/system_change")
async def change_prompts(payload: Dict[str, Any] = Body(...)):
    user_files = {
        "field_guidelines": USER_FIELD_GUIDELINES_PATH,
        "summary_system": USER_SUMMARY_SYSTEM_PROMPT_PATH,
        "summary_user_template": USER_SUMMARY_USER_TMPL_PATH,
        "qa_system": USER_QA_SYSTEM_PROMPT_PATH,
        "qa_user_template": USER_QA_USER_TMPL_PATH,
        "system": USER_SYSTEM_PROMPT_PATH,
        "user_template": USER_USER_TMPL_PATH,
    }

    if not payload:
        raise HTTPException(status_code=400, detail="Payload cannot be empty")

    invalid_keys = [key for key in payload if key not in user_files]
    if invalid_keys:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid payload keys: {', '.join(sorted(set(invalid_keys)))}",
        )

    USER_PROMPTS_DIR.mkdir(parents=True, exist_ok=True)

    for key, value in payload.items():
        if not isinstance(value, str):
            raise HTTPException(status_code=400, detail=f"Value for '{key}' must be a string")
        with user_files[key].open("w", encoding="utf-8") as file:
            file.write(value)

    return {"status": "ok"}

@app.post("/check")
async def check(
    file: UploadFile = File(None),
    payload: Optional[Dict[str, Any]] = Body(None),
    test: int = Query(0),
):
    # Accept either multipart file or JSON body {"text": "..."}
    if file is None and not payload:
        raise HTTPException(status_code=400, detail="Provide a text file or JSON body with {'text': '...'}")

    sections = None
    if file is not None:
        text, sections = await read_text_and_sections_from_upload(file)
    else:
        text = payload.get("text", "") if isinstance(payload, dict) else ""

    if not text.strip():
        raise HTTPException(status_code=400, detail="Empty text")

    if test:
        if sections is None:
            sections = [text]

        return {f"part_{idx}": part for idx, part in enumerate(sections)}

    return await _process_text_payload(text)


def _normalize_sections(payload: Dict[str, Any]) -> Dict[str, str]:
    sections_input = payload.get("sections") or payload.get("parts")

    if sections_input is None:
        text = payload.get("text", "")
        if isinstance(text, str) and text.strip():
            return {"part_0": text}
        raise HTTPException(status_code=400, detail="Provide 'sections' or non-empty 'text'")

    if isinstance(sections_input, list):
        return {
            f"part_{idx}": section if isinstance(section, str) else ""
            for idx, section in enumerate(sections_input)
        }

    if isinstance(sections_input, dict):
        normalized = {}
        for key, value in sections_input.items():
            if not isinstance(key, str):
                raise HTTPException(status_code=400, detail="Section keys must be strings")
            normalized[key] = value if isinstance(value, str) else ""
        return normalized

    raise HTTPException(status_code=400, detail="'sections' must be an object or array")


def _normalize_queries(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    queries = payload.get("queries") or payload.get("plan") or payload.get("questions")
    if not queries or not isinstance(queries, list):
        raise HTTPException(status_code=400, detail="Provide a non-empty 'queries' list")

    normalized: List[Dict[str, Any]] = []
    for item in queries:
        if not isinstance(item, dict):
            raise HTTPException(status_code=400, detail="Each query must be an object")

        parts = item.get("parts")
        question = item.get("question")
        answers = item.get("answer")

        if not isinstance(parts, list) or not all(isinstance(p, str) for p in parts):
            raise HTTPException(status_code=400, detail="Query 'parts' must be a list of strings")
        if not isinstance(question, str) or not question.strip():
            raise HTTPException(status_code=400, detail="Query 'question' must be a non-empty string")
        if not isinstance(answers, list) or not all(isinstance(a, str) for a in answers):
            raise HTTPException(status_code=400, detail="Query 'answer' must be a list of strings")

        normalized.append({"parts": parts, "question": question.strip(), "answer": answers})

    return normalized


def _load_qa_plan(plan_name: str) -> List[Dict[str, Any]]:
    """Load a predefined QA plan stored inside the project assets.

    The plan file must reside under ``assets/qa_plans`` and have a ``.json``
    extension. The JSON content can either be a raw list of query objects or
    an object with a ``queries`` key that contains that list.
    """

    safe_name = Path(plan_name).stem
    plan_path = QA_PLANS_DIR / f"{safe_name}.json"

    if not plan_path.exists():
        raise HTTPException(status_code=404, detail=f"QA plan '{safe_name}' not found")

    content = _load_json_file(plan_path)
    plan_payload = {"queries": content} if isinstance(content, list) else content

    if not isinstance(plan_payload, dict):
        raise HTTPException(status_code=400, detail="QA plan must be an object or array of queries")

    return _normalize_queries(plan_payload)


async def _run_queries(
    sections_map: Dict[str, str], queries: List[Dict[str, Any]]
) -> Dict[str, Any]:
    aggregated: Dict[str, Any] = {}
    responses: List[Dict[str, Any]] = []

    for query in queries:
        missing_parts = [name for name in query["parts"] if name not in sections_map]
        if missing_parts:
            raise HTTPException(
                status_code=400,
                detail=f"Sections not found for parts: {', '.join(sorted(set(missing_parts)))}",
            )

        combined_text = "\n\n".join(sections_map[name] for name in query["parts"])
        result = await qa_service.ask(combined_text, query["question"], query["answer"])

        responses.append({"question": query["question"], "parts": query["parts"], "result": result})
        for key, value in result.items():
            aggregated[key] = value

    return {"ok": True, "result": aggregated, "responses": responses}


@app.post("/qa")
async def ask_questions(payload: Dict[str, Any] = Body(...)):
    if qa_service is None:
        raise HTTPException(status_code=503, detail="LLM features are disabled (USE_LLM=false)")

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Payload must be an object")

    sections_map = _normalize_sections(payload)
    queries = _normalize_queries(payload)

    return await _run_queries(sections_map, queries)


@app.post("/qa/docx")
async def ask_questions_from_docx(
    file: UploadFile = File(...), plan: str = Query("default")
):
    """Run a predefined QA plan against a DOCX file.

    The endpoint splits the DOCX into ``part_0``, ``part_1``, ... sections,
    loads the specified plan from ``assets/qa_plans/<plan>.json``, and returns
    aggregated answers from the LLM.
    """

    if qa_service is None:
        raise HTTPException(status_code=503, detail="LLM features are disabled (USE_LLM=false)")

    if file is None:
        raise HTTPException(status_code=400, detail="Provide a DOCX file")

    text, sections = await read_text_and_sections_from_upload(file)
    if sections is None:
        sections = [text]

    sections_map = {f"part_{idx}": section for idx, section in enumerate(sections)}
    queries = _load_qa_plan(plan)

    return await _run_queries(sections_map, queries)
