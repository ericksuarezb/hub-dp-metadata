from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.datacontract_exporter import export_datacontract


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Genera un contrato ODCS YAML a partir del SQL analizado.")
    parser.add_argument("--sql", required=True, help="Ruta del SQL a procesar.")
    parser.add_argument("--config", required=True, help="Ruta del YAML del proyecto.")
    parser.add_argument("--output", help="Ruta del YAML de salida.")
    parser.add_argument("--profile-db", help="Ruta opcional a una base tabular de profile, preferentemente DuckDB.")
    parser.add_argument("--profile-table", help="Nombre opcional de la tabla o vista a perfilar.")
    parser.add_argument("--profile-engine", choices=["duckdb", "sqlite"], help="Motor explicito del profile.")
    parser.add_argument("--sqlite-db", help="Ruta opcional a una base SQLite para enriquecer tipos y ejemplos.")
    parser.add_argument("--sqlite-table", help="Nombre opcional de la tabla o vista SQLite a perfilar.")
    parser.add_argument("--ddl", help="Ruta opcional a una DDL de Impala para enriquecer tipos fisicos.")
    parser.add_argument("--csv-sample", help="Ruta opcional a un CSV de muestra para ejemplos y server local del CLI.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    output = args.output or str(Path("output/datacontract") / f"{Path(args.sql).stem}.yaml")
    result = export_datacontract(
        sql_path=args.sql,
        config_path=args.config,
        output_path=output,
        profile_path=args.profile_db,
        profile_table=args.profile_table,
        profile_engine=args.profile_engine,
        sqlite_path=args.sqlite_db,
        sqlite_table=args.sqlite_table,
        ddl_path=args.ddl,
        csv_path=args.csv_sample,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
