#!/bin/sh
set -eu

PROJETO_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$PROJETO_DIR"

exec python3 "$PROJETO_DIR/sistema_gt_rfid_v27_rc522.py" >> "$PROJETO_DIR/sistema_gt.log" 2>&1
