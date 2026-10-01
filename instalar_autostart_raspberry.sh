#!/bin/sh
set -eu

PROJETO_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
LAUNCHER="$PROJETO_DIR/iniciar_sistema_gt.sh"
AUTOSTART_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/autostart"
DESKTOP_FILE="$AUTOSTART_DIR/sistema-gt-rfid.desktop"

chmod +x "$LAUNCHER"
mkdir -p "$AUTOSTART_DIR"

cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=Sistema GT RFID
Comment=Sistema de controle de acesso do guincho tracionador
Exec="$LAUNCHER"
Path=$PROJETO_DIR
Terminal=false
StartupNotify=false
X-GNOME-Autostart-enabled=true
EOF

printf '%s\n' "Autostart instalado em: $DESKTOP_FILE"
printf '%s\n' "O sistema será iniciado automaticamente no próximo login do Raspberry Pi."
printf '%s\n' "Para testar agora: $LAUNCHER"
