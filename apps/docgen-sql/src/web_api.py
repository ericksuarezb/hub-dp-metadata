from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Literal, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from src.config import extract_variable_tokens
from src.duckdb_ui import ensure_duckdb_ui_server
from src.import_entropy import EntropyImporter, load_bundle, load_entropy_settings, overlay_sources_from_registry
from src.run_repository import SupabaseRunRepository, load_supabase_settings
from src.sql_business_context import infer_sql_business_context
from src.supabase_table_client import SupabaseTableClient
from src.sync_entropy_registry import build_entropy_source_registry_rows
from src.web_models import WebGenerationRequest
from src.web_service import WEB_RUNS_ROOT, execute_web_generation, preview_request

app = FastAPI(title="docgen-sql web api", version="0.1.0")
logger = logging.getLogger(__name__)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

WEB_RUNS_ROOT.mkdir(parents=True, exist_ok=True)
app.mount("/artifacts", StaticFiles(directory=str(WEB_RUNS_ROOT)), name="artifacts")


class SqlVariablesRequest(BaseModel):
    sql_text: str


class SqlBusinessContextRequest(BaseModel):
    sql_text: str
    sql_file_name: Optional[str] = None


class EntropyRunControlRequest(BaseModel):
    include_in_entropy: bool
    review_status: Literal["pending", "approved", "excluded"] = "pending"
    notes: str = ""
    complementary_actions: List[str] = Field(default_factory=list)


class EntropyRunImportRequest(BaseModel):
    execute: bool = False
    use_registry: bool = True
    refresh_registry: bool = True


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/api/duckdb-ui/start")
def start_duckdb_ui() -> dict:
    try:
        return ensure_duckdb_ui_server()
    except Exception as exc:  # pragma: no cover - thin transport wrapper
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/preview-input")
def preview(payload: WebGenerationRequest) -> dict:
    return preview_request(payload)


@app.post("/api/sql/variables")
def extract_sql_variables(payload: SqlVariablesRequest) -> dict:
    return {"variables": extract_variable_tokens(payload.sql_text)}


@app.post("/api/sql/business-context")
def infer_business_context(payload: SqlBusinessContextRequest) -> dict:
    suggestion = infer_sql_business_context(payload.sql_text, payload.sql_file_name)
    return suggestion.model_dump()


@app.post("/api/generate")
def generate(payload: WebGenerationRequest) -> dict:
    try:
        response = execute_web_generation(payload)
    except Exception as exc:  # pragma: no cover - thin transport wrapper
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    artifact_links = {}
    for key, value in response.generated_files.items():
        path = Path(value)
        relative = path.relative_to(WEB_RUNS_ROOT)
        artifact_links[key] = f"/artifacts/{relative.as_posix()}"

    data = response.model_dump()
    data["artifact_links"] = artifact_links
    return data


@app.get("/api/storage/{bucket}/{object_path:path}")
def get_storage_object(bucket: str, object_path: str):
    repository = SupabaseRunRepository(load_supabase_settings())
    if not repository.is_enabled():
        raise HTTPException(status_code=404, detail="Supabase Storage no esta configurado.")
    try:
        body, content_type = repository.download_object(bucket, object_path)
    except Exception as exc:  # pragma: no cover - thin transport wrapper
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    file_name = Path(object_path).name
    headers = {"Content-Disposition": f'inline; filename="{file_name}"'}
    return Response(content=body, media_type=content_type, headers=headers)


@app.get("/api/datacontracts/latest")
def list_latest_datacontracts(search: str = "", limit: int = 100) -> dict:
    repository = SupabaseRunRepository(load_supabase_settings())
    if not repository.is_enabled():
        raise HTTPException(status_code=404, detail="Supabase no esta configurado.")
    try:
        items = repository.list_latest_datacontracts(search=search, limit=limit)
    except Exception as exc:  # pragma: no cover - thin transport wrapper
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"items": items}


@app.get("/api/datacontracts/{run_id}")
def get_datacontract(run_id: str) -> dict:
    repository = SupabaseRunRepository(load_supabase_settings())
    if not repository.is_enabled():
        raise HTTPException(status_code=404, detail="Supabase no esta configurado.")
    try:
        item = repository.get_datacontract_version(run_id)
    except Exception as exc:  # pragma: no cover - thin transport wrapper
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not item:
        raise HTTPException(status_code=404, detail="No se encontro la version solicitada.")
    return item


@app.get("/api/entropy/runs")
def list_entropy_runs(search: str = "", limit: int = 100) -> dict:
    repository = SupabaseRunRepository(load_supabase_settings())
    if not repository.is_enabled():
        raise HTTPException(status_code=404, detail="Supabase no esta configurado.")
    try:
        items = repository.list_entropy_runs(search=search, limit=limit)
    except Exception as exc:  # pragma: no cover - thin transport wrapper
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"items": items}


@app.patch("/api/entropy/runs/{run_id}")
def update_entropy_run(run_id: str, payload: EntropyRunControlRequest) -> dict:
    repository = SupabaseRunRepository(load_supabase_settings())
    if not repository.is_enabled():
        raise HTTPException(status_code=404, detail="Supabase no esta configurado.")
    try:
        item = repository.update_entropy_run_control(
            run_id,
            include_in_entropy=payload.include_in_entropy,
            review_status=payload.review_status,
            notes=payload.notes.strip(),
            complementary_actions=[item for item in payload.complementary_actions if str(item).strip()],
        )
    except Exception as exc:  # pragma: no cover - thin transport wrapper
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return item


@app.post("/api/entropy/runs/{run_id}/import")
def import_entropy_run(run_id: str, payload: EntropyRunImportRequest) -> dict:
    repository = SupabaseRunRepository(load_supabase_settings())
    if not repository.is_enabled():
        raise HTTPException(status_code=404, detail="Supabase no esta configurado.")

    registry_rows_synced = 0
    try:
        control = repository.get_entropy_run_control(run_id)
        if not control.get("include_in_entropy"):
            raise HTTPException(
                status_code=409,
                detail="El run_id seleccionado no esta habilitado para ingesta a Entropy.",
            )

        if payload.refresh_registry:
            client = SupabaseTableClient()
            schema_map = client.fetch_schema_catalog_map()
            source_rows = build_entropy_source_registry_rows(run_id, schema_map)
            client.upsert_rows(
                "entropy_source_registry",
                source_rows,
                on_conflict="run_id,target_table,source_table",
            )
            registry_rows_synced = len(source_rows)

        bundle = load_bundle(run_id, None, latest_run=False)
        if payload.use_registry:
            bundle = overlay_sources_from_registry(bundle)

        importer = EntropyImporter(load_entropy_settings())
        result = importer.run(bundle, dry_run=not payload.execute)
        repository.save_entropy_import_result(
            run_id,
            status="executed" if payload.execute else "planned",
            result=result,
            imported=payload.execute,
        )
        return {
            "run_id": run_id,
            "registry_rows_synced": registry_rows_synced,
            "result": result,
            "control": repository.get_entropy_run_control(run_id),
        }
    except HTTPException:
        raise
    except Exception as exc:  # pragma: no cover - network/runtime dependent
        logger.exception("Entropy import failed for run_id=%s", run_id)
        error_payload = {"error": str(exc), "execute": payload.execute}
        try:
            repository.save_entropy_import_result(
                run_id,
                status="failed",
                result=error_payload,
                imported=False,
            )
        except Exception:
            pass
        raise HTTPException(status_code=400, detail=str(exc)) from exc
