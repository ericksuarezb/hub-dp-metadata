from src.export_entropy_bundle import build_entropy_bundle, split_dataset_name


def test_split_dataset_name_returns_namespace_and_name():
    namespace, name = split_dataset_name("demo.clientes")

    assert namespace == "demo"
    assert name == "clientes"


def test_build_entropy_bundle_maps_contract_assets_and_lineage():
    payload = {
        "app_run": {
            "run_id": "run-123",
            "product_name": "Clientes",
            "target_table": "demo.clientes",
            "status": "completed",
        },
        "run_analysis": {
            "analysis_json": {"target_table": "demo.clientes"},
        },
        "run_audit_summary": {"passed": True, "warning_count": 1},
        "run_audit_findings": [{"message": "warning", "severity": "warning"}],
        "run_sources": [
            {
                "source_table": "raw.personas",
                "layer": "Raw",
                "contains_description": "Tabla persona origen",
                "source_kind": "table",
            }
        ],
        "run_transformations": [{"field_name": "id_cliente"}],
        "run_modules": [
            {
                "module_key": "paso_01",
                "module_name": "Paso 01",
                "sql_file_name": "clientes.sql",
                "target_table": "demo.clientes",
                "analysis_json": {"resolved_sql": "select * from raw.personas"},
            }
        ],
        "run_module_sources": [
            {
                "module_key": "paso_01",
                "source_table": "raw.personas",
            }
        ],
        "run_pipeline_relations": [
            {
                "module_key": "paso_01",
                "source_node": "raw.personas",
                "target_node": "demo.clientes",
                "relation_label": "FROM / BASE",
            }
        ],
        "run_workspace_files": [
            {
                "relative_path": "input/sql/clientes.sql",
                "file_category": "sql",
                "size_bytes": 120,
                "storage_path": "run-123/workspace/input/sql/clientes.sql",
            }
        ],
        "datacontract_version": {
            "file_name": "demo.clientes.odcs.yaml",
            "storage_path": "run-123/demo.clientes.odcs.yaml",
            "yaml_text": "\n".join(
                [
                    "dataProduct: Clientes",
                    "status: active",
                    "domain: captacion",
                    "tags:",
                    "  - diario",
                    "schema:",
                    "  - name: clientes",
                    "    physicalName: demo.clientes",
                    "    description: Dataset clientes",
                    "    properties:",
                    "      - name: id_cliente",
                    "        logicalType: string",
                ]
            ),
        },
    }

    bundle = build_entropy_bundle(payload)

    assert bundle["data_product"]["name"] == "Clientes"
    assert bundle["data_product"]["field_count"] == 1
    assert bundle["assets"][0]["qualified_name"] == "demo.clientes"
    assert bundle["assets"][1]["qualified_name"] == "raw.personas"
    assert bundle["lineage"]["openlineage_events"][0]["job"]["name"] == "paso_01"
    assert bundle["lineage"]["openlineage_events"][0]["inputs"][0]["name"] == "personas"
