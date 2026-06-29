from __future__ import annotations

import argparse
import json
import os
import yaml
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib import error, parse, request

from pydantic import BaseModel

from src.credentials import first_non_empty, get_credential
from src.export_entropy_bundle import build_entropy_bundle
from src.run_repository import SupabaseRunRepository, load_supabase_settings
from src.runtime_paths import project_path
from src.supabase_table_client import SupabaseTableClient


class EntropyImportSettings(BaseModel):
    base_url: str = "http://127.0.0.1:8082"
    api_token_env: str = "ENTROPY_API_TOKEN"
    api_token: str = ""
    team_id_env: str = "ENTROPY_TEAM_ID"
    team_id: str = ""
    team_name_env: str = "ENTROPY_TEAM_NAME"
    team_name: str = ""
    timeout_seconds: int = 15
    publish_datacontract: bool = True


class EntropyImporter:
    def __init__(self, settings: Optional[EntropyImportSettings] = None):
        self.settings = settings or EntropyImportSettings()

    def build_import_payload(self, bundle: Dict[str, Any]) -> Dict[str, Any]:
        data_product = bundle.get("data_product") or {}
        assets = bundle.get("assets") or []
        lineage = bundle.get("lineage") or {}
        quality = bundle.get("quality") or {}
        datacontract = bundle.get("datacontract") or {}
        source_context = bundle.get("source") or {}
        registry_controlled_sources = bool(source_context.get("registry_controlled_sources"))

        datasets = [item for item in assets if item.get("asset_type") == "dataset"]
        evidence_files = [item for item in assets if item.get("asset_type") == "file"]
        target_datasets = [item for item in datasets if item.get("role") == "target"]
        source_datasets = self._normalize_source_datasets(
            [item for item in datasets if item.get("role") == "source"],
            [] if registry_controlled_sources else (lineage.get("relations") or []),
        )
        data_product_key = _normalize_identifier(data_product.get("target_table") or data_product.get("name"))
        output_port_id = _build_output_port_id(
            target_datasets[0] if target_datasets else {},
            fallback=data_product_key,
        )
        normalized_description = _normalize_description_text(data_product.get("description"))
        normalized_all_datasets = [*target_datasets, *source_datasets]
        datacontract_external_key = _build_datacontract_id(datacontract, data_product, output_port_id)

        return {
            "source": bundle.get("source") or {},
            "data_product": {
                "external_key": data_product_key,
                "name": data_product.get("name"),
                "domain": data_product.get("domain"),
                "description": normalized_description,
                "description_structured": _normalize_description_structured(data_product.get("description")),
                "status": data_product.get("status"),
                "tags": data_product.get("tags") or [],
                "schema_name": data_product.get("schema_name"),
                "schema_physical_name": data_product.get("schema_physical_name"),
                "output_port_id": output_port_id,
            },
            "datasets": {
                "target": target_datasets,
                "sources": source_datasets,
                "all": normalized_all_datasets,
            },
            "lineage": {
                "relations": lineage.get("relations") or [],
                "openlineage_events": [
                    _enrich_openlineage_event(
                        event,
                        data_product_id=data_product_key,
                        data_product_name=data_product.get("name"),
                        output_port_id=output_port_id,
                        output_port_name=target_datasets[0].get("display_name") if target_datasets else output_port_id,
                        datacontract_id=datacontract_external_key,
                        datacontract_name=datacontract.get("file_name") or datacontract_external_key,
                    )
                    for event in (lineage.get("openlineage_events") or [])
                ],
            },
            "evidence_files": evidence_files,
            "quality": {
                "summary": quality.get("summary") or {},
                "findings": quality.get("findings") or [],
            },
            "datacontract": {
                "external_key": datacontract_external_key,
                "file_name": datacontract.get("file_name"),
                "storage_path": datacontract.get("storage_path"),
                "yaml": datacontract.get("yaml") or "",
                "parsed": datacontract.get("parsed") if isinstance(datacontract.get("parsed"), dict) else None,
            },
        }

    def _normalize_source_datasets(
        self,
        datasets: List[Dict[str, Any]],
        relations: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        normalized: List[Dict[str, Any]] = []
        seen = set()
        for dataset in datasets:
            candidate = _normalize_physical_source_dataset(dataset)
            if not candidate:
                continue
            key = candidate.get("qualified_name")
            if key in seen:
                continue
            normalized.append(candidate)
            seen.add(key)
        for relation in relations:
            candidate = _build_source_dataset_from_relation(relation)
            if not candidate:
                continue
            key = candidate.get("qualified_name")
            if key in seen:
                continue
            normalized.append(candidate)
            seen.add(key)
        return normalized

    def build_operation_plan(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        datasets = payload.get("datasets") or {}
        lineage = payload.get("lineage") or {}
        quality = payload.get("quality") or {}

        return {
            "create_or_update_data_product": bool(payload.get("data_product", {}).get("name")),
            "publish_datacontract": bool((payload.get("datacontract") or {}).get("yaml")),
            "target_dataset_count": len(datasets.get("target") or []),
            "source_dataset_count": len(datasets.get("sources") or []),
            "lineage_relation_count": len(lineage.get("relations") or []),
            "openlineage_event_count": len(lineage.get("openlineage_events") or []),
            "evidence_file_count": len(payload.get("evidence_files") or []),
            "quality_finding_count": len(quality.get("findings") or []),
        }

    def build_dataproduct_request(self, payload: Dict[str, Any]) -> tuple[str, Dict[str, Any], str]:
        data_product = payload.get("data_product") or {}
        datasets = payload.get("datasets") or {}
        target_dataset = (datasets.get("target") or [{}])[0]
        source_datasets = datasets.get("sources") or []
        data_product_id = data_product.get("external_key")
        output_port_id = data_product.get("output_port_id")

        body = {
            "apiVersion": "v1.0.0",
            "kind": "DataProduct",
            "id": data_product_id,
            "name": data_product.get("name"),
            "version": "0.1.0",
            "status": _normalize_status(data_product.get("status")),
            "domain": data_product.get("domain") or "",
            "team": {
                "name": self.settings.team_id,
            },
            "description": data_product.get("description_structured") or _coerce_description_object(data_product.get("description")),
            "tags": data_product.get("tags") or [],
            "customProperties": _build_custom_properties(
                {
                    "schema_name": data_product.get("schema_name") or "",
                    "schema_physical_name": data_product.get("schema_physical_name") or "",
                    "source_system": (payload.get("source") or {}).get("system") or "",
                    "run_id": (payload.get("source") or {}).get("run_id") or "",
                    "datacontract_file_name": (payload.get("datacontract") or {}).get("file_name") or "",
                    "datacontract_storage_path": (payload.get("datacontract") or {}).get("storage_path") or "",
                    "odcs_yaml": (payload.get("datacontract") or {}).get("yaml") or "",
                    "registry_controlled_sources": bool((payload.get("source") or {}).get("registry_controlled_sources")),
                    "source_dataset_count": len(source_datasets),
                }
            ),
            "outputPorts": [
                self._build_odps_output_port(
                    target_dataset,
                    data_product,
                    output_port_id,
                    (payload.get("datacontract") or {}).get("external_key") or "",
                )
            ],
        }
        return data_product_id, body, "odps"

    def _build_odps_output_port(
        self,
        dataset: Dict[str, Any],
        data_product: Dict[str, Any],
        output_port_id: str,
        datacontract_id: str,
    ) -> Dict[str, Any]:
        qualified_name = dataset.get("qualified_name") or data_product.get("schema_physical_name") or data_product.get("name")
        output_port = {
            "name": output_port_id,
            "version": "0.1.0",
            "description": dataset.get("description") or data_product.get("description"),
            "tags": data_product.get("tags") or dataset.get("tags") or [],
            "customProperties": _build_custom_properties(
                {
                    "displayName": dataset.get("display_name") or data_product.get("name") or output_port_id,
                    "location": qualified_name,
                    "status": _normalize_status(data_product.get("status")),
                    "type": _infer_port_type(dataset),
                    "containsPii": False,
                    "qualified_name": qualified_name,
                    "role": "target",
                }
            ),
        }
        if datacontract_id:
            output_port["contractId"] = datacontract_id
            output_port["dataContractId"] = datacontract_id
        return output_port

    def execute(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        self._validate_execute_settings()
        datacontract_result = self.publish_datacontract(payload)
        data_product_id, data_product_body, specification = self.build_dataproduct_request(payload)
        query = parse.urlencode({"specification": specification})
        data_product_path = f"/api/dataproducts/{parse.quote(data_product_id, safe='')}?{query}"
        data_product_response = self._request_json("PUT", data_product_path, data_product_body)

        output_port_id = (payload.get("data_product") or {}).get("output_port_id") or ""
        lineage_results = []
        for event in (payload.get("lineage") or {}).get("openlineage_events") or []:
            query = parse.urlencode(
                {
                    "dataProductId": data_product_id,
                    "outputPortId": output_port_id,
                }
            )
            response = self._request_json("POST", f"/api/v1/lineage?{query}", event)
            lineage_results.append(
                {
                    "job_name": ((event.get("job") or {}).get("name") or ""),
                    "run_id": ((event.get("run") or {}).get("runId") or ""),
                    "response": response,
                }
            )

        return {
            "mode": "execute",
            "status": "executed",
            "data_product_id": data_product_id,
            "output_port_id": output_port_id,
            "endpoints": {
                "datacontract": datacontract_result.get("endpoint"),
                "data_product": self._build_url(data_product_path),
                "lineage": self._build_url("/api/v1/lineage"),
            },
            "results": {
                "datacontract": datacontract_result,
                "data_product": data_product_response,
                "lineage_events_sent": len(lineage_results),
                "lineage": lineage_results,
            },
        }

    def publish_datacontract(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        datacontract = payload.get("datacontract") or {}
        yaml_text = str(datacontract.get("yaml") or "").strip()
        if not yaml_text or not self.settings.publish_datacontract:
            return {
                "status": "skipped",
                "reason": "missing_yaml" if not yaml_text else "disabled",
            }

        contract_id, contract_object, normalized_yaml = self.build_datacontract_request(payload)
        attempts = [
            (
                "PUT",
                f"/api/datacontracts/{parse.quote(contract_id, safe='')}?specification=odcs",
                contract_object,
                {"Content-Type": "application/json", "Accept": "application/json"},
            ),
            (
                "PUT",
                f"/api/datacontracts/{parse.quote(contract_id, safe='')}",
                contract_object,
                {"Content-Type": "application/json", "Accept": "application/json"},
            ),
            (
                "PUT",
                f"/api/datacontracts/{parse.quote(contract_id, safe='')}?specification=odcs",
                normalized_yaml,
                {"Content-Type": "application/yaml", "Accept": "application/json"},
            ),
            (
                "PUT",
                f"/api/datacontracts/{parse.quote(contract_id, safe='')}",
                normalized_yaml,
                {"Content-Type": "application/yaml", "Accept": "application/json"},
            ),
        ]

        failures = []
        for method, path, body, headers in attempts:
            try:
                response = self._request(method, path, body, headers=headers)
                return {
                    "status": "published",
                    "contract_id": contract_id,
                    "endpoint": self._build_url(path),
                    "response": response,
                    "request_format": "json" if isinstance(body, dict) else "yaml",
                }
            except RuntimeError as exc:
                failures.append(str(exc))

        raise RuntimeError(
            "No fue posible publicar el Data Contract en Entropy. "
            f"Intentos: {' | '.join(failures)}"
        )

    def build_datacontract_request(self, payload: Dict[str, Any]) -> tuple[str, Dict[str, Any], str]:
        datacontract = payload.get("datacontract") or {}
        data_product = payload.get("data_product") or {}
        contract_object = _build_datacontract_object(datacontract, data_product)
        contract_id = _normalize_identifier(
            contract_object.get("id")
            or datacontract.get("external_key")
            or data_product.get("external_key")
            or "datacontract"
        )
        contract_object["id"] = contract_id
        if not contract_object.get("dataProduct") and data_product.get("name"):
            contract_object["dataProduct"] = data_product.get("name")
        normalized_yaml = yaml.safe_dump(contract_object, allow_unicode=True, sort_keys=False)
        return contract_id, contract_object, normalized_yaml

    def run(self, bundle: Dict[str, Any], dry_run: bool = True) -> Dict[str, Any]:
        payload = self.build_import_payload(bundle)
        plan = self.build_operation_plan(payload)
        if dry_run:
            return {
                "mode": "dry-run",
                "status": "planned",
                "plan": plan,
                "payload": payload,
            }
        executed = self.execute(payload)
        executed["plan"] = plan
        executed["payload"] = payload
        return executed

    def _validate_execute_settings(self) -> None:
        if not self.settings.base_url.strip():
            raise SystemExit("Falta ENTROPY_BASE_URL para ejecutar la importacion real.")
        if not self.settings.api_token.strip():
            raise SystemExit("Falta ENTROPY_API_TOKEN para ejecutar la importacion real.")
        if not self.settings.team_id.strip():
            resolved_team_id = self.discover_team_id()
            if not resolved_team_id:
                raise SystemExit(
                    "No fue posible resolver automaticamente el team owner. "
                    "Configura ENTROPY_TEAM_ID o ENTROPY_TEAM_NAME."
                )
            self.settings.team_id = resolved_team_id

    def discover_team_id(self) -> str:
        teams = self.list_teams()
        if not teams:
            return ""

        preferred_name = (self.settings.team_name or "").strip().lower()
        if preferred_name:
            for team in teams:
                team_id = str(team.get("id") or "").strip()
                team_name = str(team.get("name") or team.get("displayName") or "").strip().lower()
                if preferred_name in {team_id.lower(), team_name}:
                    return team_id
            available = ", ".join(
                f"{str(item.get('name') or item.get('displayName') or item.get('id') or '').strip()}"
                for item in teams
            )
            raise SystemExit(
                "No encontre un team que coincida con ENTROPY_TEAM_NAME. "
                f"Disponibles: {available}"
            )

        candidate_teams = [item for item in teams if _looks_like_team(item)]
        if len(candidate_teams) == 1:
            return str(candidate_teams[0].get("id") or "").strip()

        if len(teams) == 1:
            return str(teams[0].get("id") or "").strip()

        names = ", ".join(
            f"{str(item.get('name') or item.get('displayName') or item.get('id') or '').strip()}"
            for item in (candidate_teams or teams)
        )
        raise SystemExit(
            "Hay multiples teams en Entropy y no pude elegir uno de forma segura. "
            f"Configura ENTROPY_TEAM_NAME o ENTROPY_TEAM_ID. Candidatos: {names}"
        )

    def list_teams(self) -> List[Dict[str, Any]]:
        for path in ("/api/teams", "/api/v1/teams"):
            try:
                response = self._request_json("GET", path, None)
            except RuntimeError:
                continue
            teams = _extract_team_items(response)
            if teams:
                return teams
        return []

    def _request_json(self, method: str, path: str, payload: Optional[Any]) -> Any:
        return self._request(method, path, payload)

    def _request(
        self,
        method: str,
        path: str,
        payload: Optional[Any],
        headers: Optional[Dict[str, str]] = None,
    ) -> Any:
        body = _encode_request_body(payload)
        req = request.Request(
            self._build_url(path),
            data=body,
            method=method,
            headers={
                "x-api-key": self.settings.api_token,
                "Accept": "application/json",
                "Content-Type": "application/json",
                **(headers or {}),
            },
        )
        try:
            with request.urlopen(req, timeout=self.settings.timeout_seconds) as response:
                raw = response.read()
                if not raw:
                    return {"status_code": response.status}
                content_type = response.headers.get("Content-Type", "")
                if "application/json" in content_type:
                    return json.loads(raw.decode("utf-8"))
                return {
                    "status_code": response.status,
                    "body": raw.decode("utf-8", errors="replace"),
                }
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"Entropy devolvio HTTP {exc.code} en {self._build_url(path)}: {detail}"
            ) from exc
        except error.URLError as exc:
            raise RuntimeError(
                f"No fue posible conectar con Entropy en {self._build_url(path)}: {exc.reason}"
            ) from exc

    def _build_url(self, path: str) -> str:
        return f"{self.settings.base_url.rstrip('/')}/{path.lstrip('/')}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prepara el payload de importacion hacia Entropy CE a partir de una corrida o bundle existente."
    )
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--run-id", help="Run ID persistido en Supabase.")
    source_group.add_argument(
        "--latest-run",
        action="store_true",
        help="Usa el run_id mas reciente disponible en Supabase.",
    )
    source_group.add_argument("--bundle-path", help="Ruta a un entropy_bundle.json ya generado.")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Ejecuta la importacion real usando ENTROPY_BASE_URL, ENTROPY_API_TOKEN y ENTROPY_TEAM_ID.",
    )
    parser.add_argument(
        "--output",
        help="Ruta opcional para escribir el resultado JSON del importador.",
    )
    parser.add_argument(
        "--use-registry",
        action="store_true",
        help="Usa entropy_source_registry_ready para reconstruir sources limpias en lugar del inventario del bundle.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    bundle = load_bundle(args.run_id, args.bundle_path, latest_run=args.latest_run)
    if args.use_registry:
        bundle = overlay_sources_from_registry(bundle)
    importer = EntropyImporter(load_entropy_settings())
    result = importer.run(bundle, dry_run=not args.execute)
    rendered = json.dumps(result, indent=2, ensure_ascii=False, default=_json_default)
    if args.output:
        Path(args.output).write_text(rendered, encoding="utf-8")
    print(rendered)


def load_bundle(run_id: Optional[str], bundle_path: Optional[str], latest_run: bool = False) -> Dict[str, Any]:
    if bundle_path:
        return json.loads(Path(bundle_path).read_text(encoding="utf-8"))

    repository = SupabaseRunRepository(load_supabase_settings())
    if not repository.is_enabled():
        raise SystemExit("Supabase no esta habilitado; usa --bundle-path o configura Supabase.")
    resolved_run_id = run_id
    if latest_run:
        resolved_run_id = get_latest_run_id(repository)
    if not resolved_run_id:
        raise SystemExit("Debes indicar --run-id, --latest-run o --bundle-path.")

    payload = repository.get_run_export_payload(resolved_run_id)
    if not payload:
        raise SystemExit(f"No se encontro informacion exportable para run_id={resolved_run_id}")
    return build_entropy_bundle(payload)


def get_latest_run_id(repository: SupabaseRunRepository) -> str:
    rows = repository._fetch_json(
        f"{repository.base_url}/rest/v1/app_runs?select=run_id,created_at&order=created_at.desc&limit=1",
        headers=repository._headers({"Accept": "application/json"}),
    )
    if not isinstance(rows, list) or not rows:
        raise SystemExit("No hay corridas disponibles en Supabase para resolver --latest-run.")
    latest = rows[0] if isinstance(rows[0], dict) else {}
    run_id = str(latest.get("run_id") or "").strip()
    if not run_id:
        raise SystemExit("La ultima corrida en Supabase no contiene run_id.")
    return run_id


def load_entropy_settings() -> EntropyImportSettings:
    load_local_env_files()
    settings = EntropyImportSettings()
    settings.base_url = first_non_empty(
        os.getenv("ENTROPY_BASE_URL", ""),
        get_credential("entropy", "base_url"),
        settings.base_url,
    )
    settings.api_token = first_non_empty(
        os.getenv("ENTROPY_API_TOKEN", ""),
        os.getenv(settings.api_token_env, "") if settings.api_token_env else "",
        get_credential("entropy", "api_token"),
        get_credential("env", settings.api_token_env),
    )
    settings.team_id = first_non_empty(
        os.getenv("ENTROPY_TEAM_ID", ""),
        os.getenv(settings.team_id_env, "") if settings.team_id_env else "",
        get_credential("entropy", "team_id"),
        get_credential("env", settings.team_id_env),
    )
    settings.team_name = first_non_empty(
        os.getenv("ENTROPY_TEAM_NAME", ""),
        os.getenv(settings.team_name_env, "") if settings.team_name_env else "",
        get_credential("entropy", "team_name"),
        get_credential("env", settings.team_name_env),
    )

    return settings


def load_local_env_files() -> None:
    for candidate in _candidate_env_files():
        _load_env_file(candidate)


def _candidate_env_files() -> List[Path]:
    project_root = project_path()
    return [
        project_root / ".env",
        project_root / ".env.local",
    ]


def _load_env_file(path: Path) -> None:
    if not path.exists() or not path.is_file():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        normalized_key = key.strip()
        if not normalized_key or normalized_key in os.environ:
            continue
        normalized_value = value.strip()
        if (
            len(normalized_value) >= 2
            and normalized_value[0] == normalized_value[-1]
            and normalized_value[0] in {"'", '"'}
        ):
            normalized_value = normalized_value[1:-1]
        os.environ[normalized_key] = normalized_value


def overlay_sources_from_registry(bundle: Dict[str, Any]) -> Dict[str, Any]:
    source = bundle.get("source") or {}
    run_id = str(source.get("run_id") or "").strip()
    if not run_id:
        return bundle

    client = SupabaseTableClient()
    if not client.is_enabled():
        raise SystemExit("Supabase no esta habilitado para leer entropy_source_registry_ready.")

    rows = client.fetch_rows("entropy_source_registry_ready", {"run_id": f"eq.{run_id}"})
    registry_assets = [_registry_row_to_asset(row) for row in rows]
    registry_assets = [item for item in registry_assets if item]
    if not registry_assets:
        return bundle

    existing_assets = bundle.get("assets") or []
    target_assets = [
        item
        for item in existing_assets
        if isinstance(item, dict) and item.get("asset_type") == "dataset" and item.get("role") == "target"
    ]
    file_assets = [
        item
        for item in existing_assets
        if isinstance(item, dict) and item.get("asset_type") == "file"
    ]

    return {
        **bundle,
        "source": {
            **source,
            "registry_controlled_sources": True,
        },
        "assets": [*target_assets, *registry_assets, *file_assets],
    }


def _registry_row_to_asset(row: Dict[str, Any]) -> Dict[str, Any]:
    source_table = str(row.get("source_table") or "").strip()
    if not source_table:
        return {}
    return {
        "asset_type": "dataset",
        "qualified_name": source_table,
        "display_name": str(row.get("source_object_name") or source_table.split(".")[-1]).strip(),
        "description": None,
        "tags": [str(row.get("source_schema_type") or "").strip()] if row.get("source_schema_type") else [],
        "role": "source",
        "source_kind": row.get("source_kind") or "table",
    }


def _normalize_identifier(value: Any) -> str:
    candidate = str(value or "").strip().lower()
    if not candidate:
        return "data_product"
    normalized = []
    previous_was_separator = False
    for char in candidate:
        if char.isalnum():
            normalized.append(char)
            previous_was_separator = False
            continue
        if previous_was_separator:
            continue
        normalized.append("-")
        previous_was_separator = True
    result = "".join(normalized).strip("-")
    return result or "data_product"


def _build_output_port_id(dataset: Dict[str, Any], fallback: str) -> str:
    qualified_name = dataset.get("qualified_name") or fallback or "output"
    return f"{_normalize_identifier(qualified_name)}-port"


def _build_datacontract_id(
    datacontract: Dict[str, Any],
    data_product: Dict[str, Any],
    output_port_id: str,
) -> str:
    parsed = datacontract.get("parsed")
    if isinstance(parsed, dict):
        candidate = _normalize_identifier(parsed.get("id"))
        if candidate and candidate != "data_product":
            return candidate

    yaml_text = str(datacontract.get("yaml") or "").strip()
    if yaml_text:
        try:
            loaded = yaml.safe_load(yaml_text)
        except yaml.YAMLError:
            loaded = None
        if isinstance(loaded, dict):
            candidate = _normalize_identifier(loaded.get("id"))
            if candidate and candidate != "data_product":
                return candidate

    file_name = str(datacontract.get("file_name") or "").strip()
    if file_name:
        suffixes = [".odcs.yaml", ".yaml", ".yml"]
        normalized = file_name
        lowered = file_name.lower()
        for suffix in suffixes:
            if lowered.endswith(suffix):
                normalized = file_name[: -len(suffix)]
                break
        candidate = _normalize_identifier(normalized)
        if candidate:
            return candidate

    schema_name = str(data_product.get("schema_name") or "").strip()
    if schema_name:
        return _normalize_identifier(schema_name)

    return _normalize_identifier(output_port_id or data_product.get("external_key") or "datacontract")


def _infer_port_type(dataset: Dict[str, Any]) -> str:
    tags = {str(item).lower() for item in (dataset.get("tags") or [])}
    source_kind = str(dataset.get("source_kind") or "").lower()
    qualified_name = str(dataset.get("qualified_name") or "").lower()
    if "kafka" in tags or "topic" in source_kind:
        return "Kafka"
    if "file" in source_kind:
        return "File"
    if "postgres" in qualified_name:
        return "PostgreSQL"
    return "Dataset"


def _normalize_status(value: Any) -> str:
    candidate = str(value or "").strip().lower()
    if candidate in {"active", "proposed", "in development"}:
        return candidate
    if candidate in {"completed", "warning", "done"}:
        return "active"
    return "active"


def _normalize_description_text(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if not isinstance(value, dict):
        return ""

    parts = []
    purpose = str(value.get("purpose") or "").strip()
    usage = str(value.get("usage") or "").strip()
    limitations = str(value.get("limitations") or "").strip()
    if purpose:
        parts.append(f"Purpose: {purpose}")
    if usage:
        parts.append(f"Usage: {usage}")
    if limitations:
        parts.append(f"Limitations: {limitations}")
    return "\n\n".join(parts)


def _normalize_description_structured(value: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(value, dict):
        return None

    normalized: Dict[str, Any] = {}
    purpose = str(value.get("purpose") or "").strip()
    usage = str(value.get("usage") or "").strip()
    limitations = value.get("limitations")

    if purpose:
        normalized["purpose"] = purpose
    if usage:
        normalized["usage"] = usage
    if isinstance(limitations, list):
        limitation_list = [str(item).strip() for item in limitations if str(item).strip()]
        if limitation_list:
            normalized["limitations"] = limitation_list
    else:
        limitation_text = str(limitations or "").strip()
        if limitation_text:
            normalized["limitations"] = limitation_text
    return normalized or None


def _coerce_description_object(value: Any) -> Dict[str, Any]:
    structured = _normalize_description_structured(value)
    if structured:
        return structured

    candidate = str(value or "").strip()
    if not candidate:
        return {}
    return {"purpose": candidate}


def _build_custom_properties(values: Dict[str, Any]) -> List[Dict[str, Any]]:
    properties: List[Dict[str, Any]] = []
    for key, value in values.items():
        if value is None:
            continue
        if isinstance(value, str):
            normalized = value.strip()
            if not normalized:
                continue
            property_value: Any = normalized
        else:
            property_value = value
        properties.append(
            {
                "property": key,
                "value": property_value,
                "description": None,
            }
        )
    return properties


def _enrich_openlineage_event(
    event: Dict[str, Any],
    *,
    data_product_id: str,
    data_product_name: Any,
    output_port_id: str,
    output_port_name: Any,
    datacontract_id: str,
    datacontract_name: Any,
) -> Dict[str, Any]:
    normalized_event = dict(event)
    run = dict(normalized_event.get("run") or {})
    run_facets = dict(run.get("facets") or {})
    run_facets["entropy_data"] = {
        "_producer": "https://entropy-data.com",
        "_schemaURL": "https://entropy-data.com/spec/facets/1-0-0/EntropyDataRunFacet.json",
        "dataProductId": data_product_id,
        "outputPortId": output_port_id,
    }
    run["facets"] = run_facets
    normalized_event["run"] = run

    dataset_facet_base = {
        "_producer": "https://entropy-data.com",
        "_schemaURL": "https://entropy-data.com/spec/facets/1-0-0/EntropyDataDatasetFacet.json",
        "dataProductId": data_product_id,
        "dataProductName": data_product_name or data_product_id,
        "dataProductHref": f"/dataproducts/{data_product_id}",
        "outputPortId": output_port_id,
        "outputPortName": output_port_name or output_port_id,
        "outputPortHref": f"/dataproducts/{data_product_id}/outputports/{output_port_id}",
    }
    if datacontract_id:
        dataset_facet_base.update(
            {
                "dataContractId": datacontract_id,
                "dataContractName": datacontract_name or datacontract_id,
                "dataContractHref": f"/datacontracts/{datacontract_id}",
            }
        )

    for key in ("inputs", "outputs"):
        normalized_datasets = []
        for dataset in normalized_event.get(key) or []:
            normalized_dataset = dict(dataset)
            dataset_facets = dict(normalized_dataset.get("facets") or {})
            dataset_facets["entropy_data"] = dataset_facet_base
            normalized_dataset["facets"] = dataset_facets
            normalized_datasets.append(normalized_dataset)
        if normalized_datasets:
            normalized_event[key] = normalized_datasets

    return normalized_event


def _build_datacontract_object(datacontract: Dict[str, Any], data_product: Dict[str, Any]) -> Dict[str, Any]:
    parsed = datacontract.get("parsed")
    if isinstance(parsed, dict):
        contract_object = dict(parsed)
    else:
        yaml_text = str(datacontract.get("yaml") or "").strip()
        loaded = yaml.safe_load(yaml_text) if yaml_text else {}
        contract_object = dict(loaded) if isinstance(loaded, dict) else {}

    if not contract_object:
        raise RuntimeError("El Data Contract no contiene un YAML ODCS valido para publicar.")

    if not contract_object.get("apiVersion"):
        contract_object["apiVersion"] = "v3.1.0"
    if not contract_object.get("kind"):
        contract_object["kind"] = "DataContract"
    if not contract_object.get("id"):
        contract_object["id"] = datacontract.get("external_key") or data_product.get("external_key") or "datacontract"
    return contract_object


def _encode_request_body(payload: Optional[Any]) -> Optional[bytes]:
    if payload is None:
        return None
    if isinstance(payload, bytes):
        return payload
    if isinstance(payload, str):
        return payload.encode("utf-8")
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def _normalize_physical_source_dataset(dataset: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    source_kind = str(dataset.get("source_kind") or "").strip().lower()
    if source_kind and source_kind not in {"table", "view"}:
        return None

    qualified_name = _extract_physical_qualified_name(dataset.get("qualified_name"))
    if not qualified_name:
        return None

    return {
        **dataset,
        "qualified_name": qualified_name,
        "display_name": qualified_name.split(".")[-1],
        "source_kind": source_kind,
    }


def _build_source_dataset_from_relation(relation: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    source_kind = str(relation.get("source_kind") or "").strip().lower()
    if source_kind not in {"table", "view"}:
        return None

    qualified_name = _extract_physical_qualified_name(relation.get("source_node"))
    if not qualified_name:
        return None

    source_group = str(relation.get("source_group") or "").strip()
    tags = [source_group] if source_group else []
    return {
        "asset_type": "dataset",
        "qualified_name": qualified_name,
        "display_name": qualified_name.split(".")[-1],
        "description": None,
        "tags": tags,
        "role": "source",
        "source_kind": source_kind,
    }


def _extract_physical_qualified_name(value: Any) -> str:
    candidate = str(value or "").strip()
    if not candidate:
        return ""

    lowered = candidate.lower()
    if lowered.startswith("cte "):
        return ""
    if "subconsulta" in lowered or "derivada de" in lowered:
        return ""
    if "," in candidate:
        return ""

    normalized = candidate.split("(")[0].strip()
    normalized = normalized.split(" AS ")[0].strip()
    normalized = normalized.split(" as ")[0].strip()

    if " " in normalized:
        return ""
    if normalized.count(".") < 1:
        return ""
    return normalized


def _extract_team_items(response: Any) -> List[Dict[str, Any]]:
    if isinstance(response, list):
        return [item for item in response if isinstance(item, dict)]
    if isinstance(response, dict):
        for key in ("items", "content", "teams", "data"):
            value = response.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def _looks_like_team(item: Dict[str, Any]) -> bool:
    team_type = str(
        item.get("teamType")
        or item.get("type")
        or item.get("kind")
        or ""
    ).strip().lower()
    if not team_type:
        return True
    return team_type in {"team", "platform team", "enabling team", "governance group"}


def _json_default(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    raise TypeError(f"Object of type {value.__class__.__name__} is not JSON serializable")


if __name__ == "__main__":
    main()
