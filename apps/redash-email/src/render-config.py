#!/usr/bin/python3

import os
import sys
from string import Template


def _recipients_yaml(raw: str) -> str:
    recipients = [item.strip() for item in raw.split(",") if item.strip()]
    if not recipients:
        recipients = ["stakeholders@local.test"]
    return "".join(f"      - {recipient}\n" for recipient in recipients)


def main() -> int:
    if len(sys.argv) != 3:
        raise SystemExit("usage: render-config.py TEMPLATE OUTPUT")

    template_path, output_path = sys.argv[1], sys.argv[2]
    mapping = {
        "REDASH_EXPORT_REDASH_URL": os.getenv(
            "REDASH_EXPORT_REDASH_URL", "http://redash-server:5000"
        ),
        "REDASH_EXPORT_API_KEY": os.getenv("REDASH_EXPORT_API_KEY", ""),
        "REDASH_EXPORT_DASHBOARD": os.getenv(
            "REDASH_EXPORT_DASHBOARD", "BAZ | CAPTACION MOCK"
        ),
        "REDASH_EXPORT_RECIPIENTS": os.getenv(
            "REDASH_EXPORT_RECIPIENTS", "stakeholders@local.test"
        ),
        "REDASH_EXPORT_RECIPIENTS_YAML": _recipients_yaml(
            os.getenv("REDASH_EXPORT_RECIPIENTS", "stakeholders@local.test")
        ),
        "REDASH_EXPORT_SENDER": os.getenv(
            "REDASH_EXPORT_SENDER", "Redash Export <redash@local.test>"
        ),
        "REDASH_EXPORT_MAILHOST_URL": os.getenv(
            "REDASH_EXPORT_MAILHOST_URL", "smtp://mailhog:1025"
        ),
        "REDASH_EXPORT_RENDER_DELAY": os.getenv("REDASH_EXPORT_RENDER_DELAY", "2"),
        "REDASH_EXPORT_NAVIGATION_TIMEOUT": os.getenv(
            "REDASH_EXPORT_NAVIGATION_TIMEOUT", "300"
        ),
    }

    with open(template_path, "r", encoding="utf-8") as fh:
        rendered = Template(fh.read()).safe_substitute(mapping)
    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
