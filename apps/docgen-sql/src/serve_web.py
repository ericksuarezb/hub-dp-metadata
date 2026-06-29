from __future__ import annotations

import argparse

import uvicorn


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Levanta la API web de docgen-sql.")
    parser.add_argument("--host", default="127.0.0.1", help="Host de escucha.")
    parser.add_argument("--port", type=int, default=8000, help="Puerto de escucha.")
    parser.add_argument("--reload", action="store_true", help="Activa autoreload para desarrollo.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    uvicorn.run("src.web_api:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
