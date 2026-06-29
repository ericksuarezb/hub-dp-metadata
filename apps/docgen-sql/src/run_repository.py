from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib import error, request
from urllib.parse import quote

import yaml
from pydantic import BaseModel

from src.credentials import first_non_empty, get_credential
from src.models import AuditResult, SqlAnalysis
from src.runtime_paths import project_path
from src.web_models import WebGenerationRequest, WebGenerationResponse

SUPABASE_CONFIG_PATH = project_path("config", "supabase.yml")


class SupabaseSettings(BaseModel):
    enabled: bool = False
    url: str = ""
    service_role_key_env: str = "SUPABASE_SERVICE_ROLE_KEY"
    service_role_key: str = ""
    timeout_seconds: int = 10
    storage_enabled: bool = False
    storage_bucket: str = "docgen-artifacts"


def load_supabase_settings(config_path: Path = SUPABASE_CONFIG_PATH) -> SupabaseSettings:
    if not config_path.exists():
        return SupabaseSettings()

    raw_data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    supabase_data = raw_data.get("supabase") if isinstance(raw_data, dict) and "supabase" in raw_data else raw_data
    return SupabaseSettings(**(supabase_data or {}))


class SupabaseRunRepository:
    def __init__(self, settings: SupabaseSettings):
        self.settings = settings
        self.base_url = settings.url.rstrip("/")
        self.service_role_key = self._resolve_service_role_key(settings)

    def is_enabled(self) -> bool:
        return self.settings.enabled and bool(self.base_url) and bool(self.service_role_key)

    def persist_run(
        self,
        run_id: str,
        request_payload: WebGenerationRequest,
        response_payload: WebGenerationResponse,
        analysis: SqlAnalysis,
        audit: AuditResult,
        odcs_yaml_text: Optional[str],
        config_snapshot: Dict[str, Any],
        module_results: Optional[List[Dict[str, Any]]] = None,
        pipeline_graph: Optional[Dict[str, Any]] = None,
        workspace_inventory: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, str]:
        if not self.is_enabled():
            return {}

        storage_objects = self._upload_artifacts(run_id, response_payload.generated_files)
        persisted_workspace_inventory = self._upload_workspace_files(run_id, workspace_inventory or [])

        app_run = {
            "run_id": run_id,
            "mode": response_payload.mode,
            "status": "completed" if audit.passed else "warning",
            "product_name": request_payload.product_name,
            "sql_file_name": Path(response_payload.sql_file).name,
            "final_table_name": request_payload.final_table_name,
            "target_table": analysis.target_table,
            "audit_passed": audit.passed,
            "generated_files": response_payload.generated_files,
            "storage_objects": storage_objects,
            "stats": response_payload.stats,
            "config_snapshot": config_snapshot,
        }
        self._upsert("app_runs", app_run, on_conflict="run_id")
        self._ensure_entropy_run_control(run_id)

        self._upsert(
            "run_analysis",
            {
                "run_id": run_id,
                "analysis_json": analysis.model_dump(mode="json"),
                "odcs_yaml": odcs_yaml_text,
                "pipeline_mermaid": (pipeline_graph or {}).get("mermaid"),
            },
            on_conflict="run_id",
        )

        self._delete_where("run_sources", {"run_id": f"eq.{run_id}"})
        self._insert_many(
            "run_sources",
            [
                {
                    "run_id": run_id,
                    "source_alias": source.alias,
                    "source_table": source.table_name,
                    "source_kind": source.source_kind,
                    "layer": source.layer,
                    "used_in_steps": source.used_in_steps,
                }
                for source in analysis.sources
            ],
        )

        self._delete_where("run_transformations", {"run_id": f"eq.{run_id}"})
        self._insert_many(
            "run_transformations",
            [
                {
                    "run_id": run_id,
                    "field_name": item.field_name,
                    "expression_name": item.expression_name,
                    "field_type": item.field_type,
                    "origin": item.origin,
                    "source_fields": item.source_fields,
                    "physical_source_fields": item.physical_source_fields,
                    "step_name": item.step,
                    "rule_id": item.rule_id,
                }
                for item in analysis.transformations
            ],
        )

        audit_json = {
            "passed": audit.passed,
            "errors": audit.errors,
            "warnings": audit.warnings,
        }
        self._upsert(
            "run_audit_summary",
            {
                "run_id": run_id,
                "passed": audit.passed,
                "error_count": len(audit.errors),
                "warning_count": len(audit.warnings),
                "audit_json": audit_json,
            },
            on_conflict="run_id",
        )

        self._delete_where("run_audit_findings", {"run_id": f"eq.{run_id}"})
        findings = [
            {"run_id": run_id, "finding_type": "audit", "severity": "error", "message": message}
            for message in audit.errors
        ] + [
            {"run_id": run_id, "finding_type": "audit", "severity": "warning", "message": message}
            for message in audit.warnings
        ]
        self._insert_many("run_audit_findings", findings)
        self._persist_module_results(run_id, module_results or [])
        self._persist_pipeline_relations(run_id, module_results or [], pipeline_graph or {})
        self._persist_workspace_inventory(run_id, persisted_workspace_inventory)
        return {
            **storage_objects,
            **{
                f"workspace::{item['relative_path']}": item["storage_path"]
                for item in persisted_workspace_inventory
                if item.get("storage_path")
            },
        }

    def list_entropy_runs(self, search: str = "", limit: int = 100) -> List[Dict[str, Any]]:
        if not self.is_enabled():
            return []

        app_runs = self._fetch_json(
            f"{self.base_url}/rest/v1/app_runs"
            "?select=run_id,created_at,product_name,sql_file_name,final_table_name,target_table,audit_passed,stats"
            "&order=created_at.desc"
            "&limit=500",
            headers=self._headers({"Accept": "application/json"}),
        )
        if not isinstance(app_runs, list) or not app_runs:
            return []

        run_ids = [str(row.get("run_id") or "").strip() for row in app_runs if row.get("run_id")]
        controls_by_run: Dict[str, Dict[str, Any]] = {}
        if run_ids:
            encoded_run_ids = ",".join(quote(run_id, safe="-_.") for run_id in run_ids)
            try:
                control_rows = self._fetch_json(
                    f"{self.base_url}/rest/v1/entropy_run_registry"
                    f"?select=*&run_id=in.({encoded_run_ids})",
                    headers=self._headers({"Accept": "application/json"}),
                )
                controls_by_run = {
                    str(row.get("run_id") or "").strip(): row
                    for row in (control_rows if isinstance(control_rows, list) else [])
                    if isinstance(row, dict) and row.get("run_id")
                }
            except RuntimeError as exc:
                if not self._is_missing_entropy_run_registry_error(exc):
                    raise

        normalized_search = search.strip().lower()
        items: List[Dict[str, Any]] = []
        for row in app_runs:
            run_id = str(row.get("run_id") or "").strip()
            if not run_id:
                continue
            control = controls_by_run.get(run_id) or self._default_entropy_run_control(run_id)
            stats = row.get("stats") if isinstance(row.get("stats"), dict) else {}
            merged = {
                "run_id": run_id,
                "created_at": row.get("created_at"),
                "product_name": row.get("product_name"),
                "sql_file_name": row.get("sql_file_name"),
                "final_table_name": row.get("final_table_name"),
                "target_table": row.get("target_table"),
                "audit_passed": bool(row.get("audit_passed")),
                "source_count": int(stats.get("sources") or 0),
                "transformation_count": int(stats.get("transformations") or 0),
                "include_in_entropy": bool(control.get("include_in_entropy")),
                "review_status": control.get("review_status") or "pending",
                "complementary_actions": control.get("complementary_actions") or [],
                "notes": control.get("notes") or "",
                "last_import_status": control.get("last_import_status") or "idle",
                "last_operation_at": control.get("last_operation_at"),
                "last_imported_at": control.get("last_imported_at"),
                "last_import_result": control.get("last_import_result") or {},
            }
            if normalized_search:
                haystack = " ".join(
                    [
                        str(merged.get("run_id") or ""),
                        str(merged.get("product_name") or ""),
                        str(merged.get("sql_file_name") or ""),
                        str(merged.get("target_table") or ""),
                        str(merged.get("notes") or ""),
                    ]
                ).lower()
                if normalized_search not in haystack:
                    continue
            items.append(merged)
            if len(items) >= limit:
                break

        return items

    def get_entropy_run_control(self, run_id: str) -> Dict[str, Any]:
        if not self.is_enabled():
            return {}
        encoded_run_id = quote(run_id.strip(), safe="-_.")
        try:
            rows = self._fetch_json(
                f"{self.base_url}/rest/v1/entropy_run_registry?select=*&run_id=eq.{encoded_run_id}&limit=1",
                headers=self._headers({"Accept": "application/json"}),
            )
        except RuntimeError as exc:
            if self._is_missing_entropy_run_registry_error(exc):
                return self._default_entropy_run_control(run_id)
            raise
        if isinstance(rows, list) and rows and isinstance(rows[0], dict):
            return rows[0]
        return self._default_entropy_run_control(run_id)

    def update_entropy_run_control(
        self,
        run_id: str,
        *,
        include_in_entropy: Optional[bool] = None,
        review_status: Optional[str] = None,
        complementary_actions: Optional[List[str]] = None,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        self._ensure_entropy_run_control(run_id)
        current = self.get_entropy_run_control(run_id)
        payload = {
            "run_id": run_id,
            "include_in_entropy": current.get("include_in_entropy") if include_in_entropy is None else include_in_entropy,
            "review_status": (current.get("review_status") or "pending") if review_status is None else review_status,
            "complementary_actions": (current.get("complementary_actions") or []) if complementary_actions is None else complementary_actions,
            "notes": (current.get("notes") or "") if notes is None else notes,
            "updated_at": self._now_iso(),
        }
        self._upsert("entropy_run_registry", payload, on_conflict="run_id")
        return self.get_entropy_run_control(run_id)

    def save_entropy_import_result(
        self,
        run_id: str,
        *,
        status: str,
        result: Dict[str, Any],
        imported: bool = False,
    ) -> Dict[str, Any]:
        self._ensure_entropy_run_control(run_id)
        payload: Dict[str, Any] = {
            "run_id": run_id,
            "last_import_status": status,
            "last_operation_at": self._now_iso(),
            "last_import_result": result,
            "updated_at": self._now_iso(),
        }
        if imported:
            payload["last_imported_at"] = self._now_iso()
        self._upsert("entropy_run_registry", payload, on_conflict="run_id")
        return self.get_entropy_run_control(run_id)

    def _persist_module_results(self, run_id: str, module_results: List[Dict[str, Any]]) -> None:
        self._delete_where("run_module_transformations", {"run_id": f"eq.{run_id}"})
        self._delete_where("run_module_sources", {"run_id": f"eq.{run_id}"})
        self._delete_where("run_modules", {"run_id": f"eq.{run_id}"})

        module_rows: List[Dict[str, Any]] = []
        source_rows: List[Dict[str, Any]] = []
        transformation_rows: List[Dict[str, Any]] = []

        for item in module_results:
            analysis: SqlAnalysis = item["analysis"]
            module_key = item["module_key"]
            module_rows.append(
                {
                    "run_id": run_id,
                    "module_key": module_key,
                    "sql_file_name": item["sql_file_name"],
                    "module_name": item["module_name"],
                    "is_step": item["is_step"],
                    "is_principal": item["is_principal"],
                    "target_table": analysis.target_table,
                    "analysis_json": analysis.model_dump(mode="json"),
                }
            )
            source_rows.extend(
                [
                    {
                        "run_id": run_id,
                        "module_key": module_key,
                        "source_alias": source.alias,
                        "source_table": source.table_name,
                        "source_kind": source.source_kind,
                        "layer": source.layer,
                        "used_in_steps": source.used_in_steps,
                    }
                    for source in analysis.sources
                ]
            )
            transformation_rows.extend(
                [
                    {
                        "run_id": run_id,
                        "module_key": module_key,
                        "field_name": transformation.field_name,
                        "expression_name": transformation.expression_name,
                        "field_type": transformation.field_type,
                        "origin": transformation.origin,
                        "source_fields": transformation.source_fields,
                        "physical_source_fields": transformation.physical_source_fields,
                        "step_name": transformation.step,
                        "rule_id": transformation.rule_id,
                    }
                    for transformation in analysis.transformations
                ]
            )

        self._insert_many("run_modules", module_rows)
        self._insert_many("run_module_sources", source_rows)
        self._insert_many("run_module_transformations", transformation_rows)

    def _persist_pipeline_relations(
        self,
        run_id: str,
        module_results: List[Dict[str, Any]],
        pipeline_graph: Dict[str, Any],
    ) -> None:
        self._delete_where("run_pipeline_relations", {"run_id": f"eq.{run_id}"})
        module_names = {item["module_key"]: item["module_name"] for item in module_results}
        sql_names = {item["module_key"]: item["sql_file_name"] for item in module_results}
        self._insert_many(
            "run_pipeline_relations",
            [
                {
                    "run_id": run_id,
                    "module_key": relation["module_key"],
                    "module_name": module_names.get(relation["module_key"], relation.get("module_name")),
                    "sql_file_name": sql_names.get(relation["module_key"], relation.get("sql_file_name")),
                    "source_node": relation["source_node"],
                    "target_node": relation["target_node"],
                    "relation_label": relation["relation_label"],
                    "source_group": relation["source_group"],
                    "target_group": relation["target_group"],
                    "source_kind": relation.get("source_kind", "table"),
                    "target_kind": relation.get("target_kind", "table"),
                    "is_pivot": relation.get("is_pivot", False),
                }
                for relation in pipeline_graph.get("relations", [])
            ],
        )

    def _persist_workspace_inventory(self, run_id: str, workspace_inventory: List[Dict[str, Any]]) -> None:
        self._delete_where("run_workspace_files", {"run_id": f"eq.{run_id}"})
        self._insert_many(
            "run_workspace_files",
            [
                {
                    "run_id": run_id,
                    "relative_path": item["relative_path"],
                    "file_category": item["file_category"],
                    "size_bytes": item["size_bytes"],
                    "storage_path": item.get("storage_path"),
                }
                for item in workspace_inventory
            ],
        )

    def _upload_workspace_files(self, run_id: str, workspace_inventory: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not self.settings.storage_enabled or not self.settings.storage_bucket:
            return workspace_inventory

        persisted: List[Dict[str, Any]] = []
        for item in workspace_inventory:
            local_path = item.get("local_path")
            if not local_path:
                persisted.append(item)
                continue
            path = Path(local_path)
            if not path.exists():
                persisted.append(item)
                continue
            object_name = f"{run_id}/workspace/{item['relative_path']}"
            self._upload_object(self.settings.storage_bucket, object_name, path)
            persisted.append(
                {
                    **item,
                    "storage_path": object_name,
                }
            )
        return persisted

    def _resolve_service_role_key(self, settings: SupabaseSettings) -> str:
        configured = (settings.service_role_key or "").strip()
        if configured:
            return configured
        env_name = (settings.service_role_key_env or "").strip()
        return first_non_empty(
            os.getenv(env_name, "") if env_name else "",
            get_credential("supabase", "service_role_key"),
            get_credential("env", env_name),
        )

    def _upsert(self, table: str, payload: Dict[str, Any], on_conflict: str) -> None:
        endpoint = f"{self.base_url}/rest/v1/{table}?on_conflict={on_conflict}"
        headers = self._headers({"Prefer": "resolution=merge-duplicates,return=minimal"})
        self._request_json("POST", endpoint, payload, headers=headers)

    def _insert_if_missing(self, table: str, payload: Dict[str, Any], on_conflict: str) -> None:
        endpoint = f"{self.base_url}/rest/v1/{table}?on_conflict={on_conflict}"
        headers = self._headers({"Prefer": "resolution=ignore-duplicates,return=minimal"})
        self._request_json("POST", endpoint, payload, headers=headers)

    def _insert_many(self, table: str, rows: List[Dict[str, Any]]) -> None:
        if not rows:
            return
        endpoint = f"{self.base_url}/rest/v1/{table}"
        headers = self._headers({"Prefer": "return=minimal"})
        self._request_json("POST", endpoint, rows, headers=headers)

    def _delete_where(self, table: str, filters: Dict[str, str]) -> None:
        query = "&".join(f"{key}={value}" for key, value in filters.items())
        endpoint = f"{self.base_url}/rest/v1/{table}?{query}"
        headers = self._headers({"Prefer": "return=minimal"})
        self._request_json("DELETE", endpoint, None, headers=headers)

    def _headers(self, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        headers = {
            "apikey": self.service_role_key,
            "Authorization": f"Bearer {self.service_role_key}",
            "Content-Type": "application/json",
        }
        if extra:
            headers.update(extra)
        return headers

    def _upload_artifacts(self, run_id: str, generated_files: Dict[str, str]) -> Dict[str, str]:
        if not self.settings.storage_enabled or not self.settings.storage_bucket:
            return {}

        uploaded: Dict[str, str] = {}
        for key, local_path in generated_files.items():
            if not self._should_upload_artifact(local_path):
                continue
            path = Path(local_path)
            if not path.exists():
                continue
            object_name = f"{run_id}/{path.name}"
            self._upload_object(self.settings.storage_bucket, object_name, path)
            uploaded[key] = object_name
        return uploaded

    def _should_upload_artifact(self, local_path: str) -> bool:
        lowered = local_path.lower()
        return (
            lowered.endswith(".docx")
            or lowered.endswith(".odcs.yaml")
            or lowered.endswith(".png")
            or lowered.endswith(".mmd")
        )

    def _upload_object(self, bucket: str, object_name: str, path: Path) -> None:
        endpoint = f"{self.base_url}/storage/v1/object/{bucket}/{object_name}"
        headers = self._headers(
            {
                "x-upsert": "true",
                "Content-Type": _content_type_for_path(path),
            }
        )
        body = path.read_bytes()
        req = request.Request(endpoint, data=body, method="POST", headers=headers)
        try:
            with request.urlopen(req, timeout=self.settings.timeout_seconds) as response:
                response.read()
        except error.HTTPError as exc:  # pragma: no cover - network/runtime dependent
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Supabase Storage devolvio HTTP {exc.code} en {endpoint}: {detail}") from exc
        except error.URLError as exc:  # pragma: no cover - network/runtime dependent
            raise RuntimeError(f"No fue posible conectar con Supabase Storage en {endpoint}: {exc.reason}") from exc

    def download_object(self, bucket: str, object_name: str) -> tuple[bytes, str]:
        endpoint = f"{self.base_url}/storage/v1/object/{bucket}/{object_name}"
        headers = self._headers()
        req = request.Request(endpoint, method="GET", headers=headers)
        try:
            with request.urlopen(req, timeout=self.settings.timeout_seconds) as response:
                content_type = response.headers.get("Content-Type", "application/octet-stream")
                return response.read(), content_type
        except error.HTTPError as exc:  # pragma: no cover - network/runtime dependent
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Supabase Storage devolvio HTTP {exc.code} en {endpoint}: {detail}") from exc
        except error.URLError as exc:  # pragma: no cover - network/runtime dependent
            raise RuntimeError(f"No fue posible conectar con Supabase Storage en {endpoint}: {exc.reason}") from exc

    def list_latest_datacontracts(self, search: str = "", limit: int = 100) -> List[Dict[str, Any]]:
        if not self.is_enabled():
            return []

        app_runs = self._fetch_json(
            f"{self.base_url}/rest/v1/app_runs"
            "?select=run_id,created_at,product_name,sql_file_name,final_table_name,target_table,storage_objects"
            "&order=created_at.desc"
            "&limit=500",
            headers=self._headers({"Accept": "application/json"}),
        )
        if not isinstance(app_runs, list) or not app_runs:
            return []

        run_ids = [str(row.get("run_id", "")).strip() for row in app_runs if row.get("run_id")]
        if not run_ids:
            return []

        encoded_run_ids = ",".join(quote(run_id, safe="-_." ) for run_id in run_ids)
        analysis_rows = self._fetch_json(
            f"{self.base_url}/rest/v1/run_analysis"
            f"?select=run_id,odcs_yaml&run_id=in.({encoded_run_ids})",
            headers=self._headers({"Accept": "application/json"}),
        )
        analysis_by_run = {
            str(row.get("run_id")): row
            for row in (analysis_rows if isinstance(analysis_rows, list) else [])
            if row.get("run_id")
        }

        normalized_search = search.strip().lower()
        latest_by_table: Dict[str, Dict[str, Any]] = {}
        for row in app_runs:
            run_id = str(row.get("run_id", "")).strip()
            if not run_id:
                continue
            table_name = str(row.get("target_table") or row.get("final_table_name") or "").strip()
            if not table_name:
                continue
            analysis_row = analysis_by_run.get(run_id, {})
            storage_objects = row.get("storage_objects") if isinstance(row.get("storage_objects"), dict) else {}
            storage_path = storage_objects.get("datacontract_yaml")
            odcs_yaml = analysis_row.get("odcs_yaml")
            if not storage_path and not odcs_yaml:
                continue

            if normalized_search:
                haystack = " ".join(
                    [
                        table_name,
                        str(row.get("product_name") or ""),
                        str(row.get("sql_file_name") or ""),
                        str(storage_path or ""),
                    ]
                ).lower()
                if normalized_search not in haystack:
                    continue

            table_key = table_name.lower()
            if table_key in latest_by_table:
                continue

            latest_by_table[table_key] = {
                "run_id": run_id,
                "table_name": table_name,
                "product_name": row.get("product_name"),
                "sql_file_name": row.get("sql_file_name"),
                "updated_at": row.get("created_at"),
                "file_name": Path(storage_path).name if storage_path else _build_datacontract_file_name(table_name),
                "storage_path": storage_path,
                "has_inline_yaml": bool(odcs_yaml),
            }
            if len(latest_by_table) >= limit:
                break

        return list(latest_by_table.values())

    def get_datacontract_version(self, run_id: str) -> Dict[str, Any]:
        if not self.is_enabled():
            return {}

        encoded_run_id = quote(run_id.strip(), safe="-_.")
        app_runs = self._fetch_json(
            f"{self.base_url}/rest/v1/app_runs"
            "?select=run_id,created_at,product_name,sql_file_name,final_table_name,target_table,storage_objects"
            f"&run_id=eq.{encoded_run_id}"
            "&limit=1",
            headers=self._headers({"Accept": "application/json"}),
        )
        row = app_runs[0] if isinstance(app_runs, list) and app_runs else None
        if not isinstance(row, dict):
            return {}

        analysis_rows = self._fetch_json(
            f"{self.base_url}/rest/v1/run_analysis"
            f"?select=run_id,odcs_yaml&run_id=eq.{encoded_run_id}"
            "&limit=1",
            headers=self._headers({"Accept": "application/json"}),
        )
        analysis_row = analysis_rows[0] if isinstance(analysis_rows, list) and analysis_rows else {}
        storage_objects = row.get("storage_objects") if isinstance(row.get("storage_objects"), dict) else {}
        table_name = str(row.get("target_table") or row.get("final_table_name") or "").strip()
        storage_path = storage_objects.get("datacontract_yaml")
        yaml_text = analysis_row.get("odcs_yaml") or ""
        if not yaml_text and storage_path and self.settings.storage_bucket:
            body, _ = self.download_object(self.settings.storage_bucket, storage_path)
            yaml_text = body.decode("utf-8", errors="replace")

        return {
            "run_id": row.get("run_id"),
            "table_name": table_name,
            "product_name": row.get("product_name"),
            "sql_file_name": row.get("sql_file_name"),
            "updated_at": row.get("created_at"),
            "file_name": Path(storage_path).name if storage_path else _build_datacontract_file_name(table_name),
            "storage_path": storage_path,
            "yaml_text": yaml_text,
        }

    def get_run_export_payload(self, run_id: str) -> Dict[str, Any]:
        if not self.is_enabled():
            return {}

        encoded_run_id = quote(run_id.strip(), safe="-_.")

        app_runs = self._fetch_json(
            f"{self.base_url}/rest/v1/app_runs?select=*&run_id=eq.{encoded_run_id}&limit=1",
            headers=self._headers({"Accept": "application/json"}),
        )
        app_run = app_runs[0] if isinstance(app_runs, list) and app_runs else None
        if not isinstance(app_run, dict):
            return {}

        return {
            "app_run": app_run,
            "run_analysis": self._fetch_first("run_analysis", encoded_run_id),
            "run_audit_summary": self._fetch_first("run_audit_summary", encoded_run_id),
            "run_audit_findings": self._fetch_many("run_audit_findings", encoded_run_id),
            "run_sources": self._fetch_many("run_sources", encoded_run_id),
            "run_transformations": self._fetch_many("run_transformations", encoded_run_id),
            "run_modules": self._fetch_many("run_modules", encoded_run_id),
            "run_module_sources": self._fetch_many("run_module_sources", encoded_run_id),
            "run_module_transformations": self._fetch_many("run_module_transformations", encoded_run_id),
            "run_pipeline_relations": self._fetch_many("run_pipeline_relations", encoded_run_id),
            "run_workspace_files": self._fetch_many("run_workspace_files", encoded_run_id),
            "datacontract_version": self.get_datacontract_version(run_id),
        }

    def _fetch_first(self, table: str, encoded_run_id: str) -> Dict[str, Any]:
        rows = self._fetch_json(
            f"{self.base_url}/rest/v1/{table}?select=*&run_id=eq.{encoded_run_id}&limit=1",
            headers=self._headers({"Accept": "application/json"}),
        )
        return rows[0] if isinstance(rows, list) and rows and isinstance(rows[0], dict) else {}

    def _fetch_many(self, table: str, encoded_run_id: str) -> List[Dict[str, Any]]:
        rows = self._fetch_json(
            f"{self.base_url}/rest/v1/{table}?select=*&run_id=eq.{encoded_run_id}&order=id.asc",
            headers=self._headers({"Accept": "application/json"}),
        )
        if not isinstance(rows, list):
            return []
        return [row for row in rows if isinstance(row, dict)]

    def _fetch_json(self, endpoint: str, headers: Dict[str, str]) -> Any:
        req = request.Request(endpoint, method="GET", headers=headers)
        try:
            with request.urlopen(req, timeout=self.settings.timeout_seconds) as response:
                body = response.read()
                if not body:
                    return None
                return json.loads(body.decode("utf-8"))
        except error.HTTPError as exc:  # pragma: no cover - network/runtime dependent
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Supabase devolvio HTTP {exc.code} en {endpoint}: {detail}") from exc
        except error.URLError as exc:  # pragma: no cover - network/runtime dependent
            raise RuntimeError(f"No fue posible conectar con Supabase en {endpoint}: {exc.reason}") from exc

    def _ensure_entropy_run_control(self, run_id: str) -> None:
        self._raise_if_missing_entropy_run_registry()
        self._insert_if_missing(
            "entropy_run_registry",
            self._default_entropy_run_control(run_id),
            on_conflict="run_id",
        )

    def _default_entropy_run_control(self, run_id: str) -> Dict[str, Any]:
        timestamp = self._now_iso()
        return {
            "run_id": run_id,
            "include_in_entropy": False,
            "review_status": "pending",
            "complementary_actions": [],
            "notes": "",
            "last_import_status": "idle",
            "last_import_result": {},
            "created_at": timestamp,
            "updated_at": timestamp,
        }

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _raise_if_missing_entropy_run_registry(self) -> None:
        try:
            self._fetch_json(
                f"{self.base_url}/rest/v1/entropy_run_registry?select=run_id&limit=1",
                headers=self._headers({"Accept": "application/json"}),
            )
        except RuntimeError as exc:
            if self._is_missing_entropy_run_registry_error(exc):
                raise RuntimeError(
                    "Falta aplicar la migracion de Supabase para `entropy_run_registry`. "
                    "Aplica la migration `20260521110000_add_entropy_run_registry.sql` y vuelve a intentar."
                ) from exc
            raise

    def _is_missing_entropy_run_registry_error(self, exc: RuntimeError) -> bool:
        message = str(exc)
        return "PGRST205" in message and "entropy_run_registry" in message

    def _request_json(
        self,
        method: str,
        endpoint: str,
        payload: Optional[Any],
        headers: Dict[str, str],
    ) -> None:
        body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = request.Request(endpoint, data=body, method=method, headers=headers)
        try:
            with request.urlopen(req, timeout=self.settings.timeout_seconds) as response:
                response.read()
        except error.HTTPError as exc:  # pragma: no cover - network/runtime dependent
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Supabase devolvio HTTP {exc.code} en {endpoint}: {detail}") from exc
        except error.URLError as exc:  # pragma: no cover - network/runtime dependent
            raise RuntimeError(f"No fue posible conectar con Supabase en {endpoint}: {exc.reason}") from exc


def _content_type_for_path(path: Path) -> str:
    lowered = path.name.lower()
    if lowered.endswith(".docx"):
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    if lowered.endswith(".yaml") or lowered.endswith(".yml"):
        return "application/yaml"
    return "application/octet-stream"


def _build_datacontract_file_name(table_name: str) -> str:
    candidate = (table_name or "datacontract").strip()
    if not candidate:
        candidate = "datacontract"
    safe = "".join(char if char.isalnum() or char in "._-" else "_" for char in candidate).strip("._")
    return f"{safe or 'datacontract'}.odcs.yaml"
