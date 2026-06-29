#!/bin/sh
set -eu

python3 /home/automation/render-config.py \
  /home/automation/templates/report.yaml.tmpl \
  /tmp/report.yaml

exec /home/automation/send-report.py /tmp/report.yaml "$@"
