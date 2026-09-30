#!/bin/sh
set -eu

PROJETO_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
LAUNCHER="$PROJETO_DIR/iniciar_sistema_gt.sh"
AUTOSTART_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/autostart"
DESKTOP_FILE="$AUTOSTART_DIR/sistema-gt-rfid.desktop"
LXDE_AUTOSTART="$HOME/.config/lxsession/LXDE-pi/autostart"
BACKUP_DIR="$HOME/.config/sistema-gt-autostart-backup-$(date +%Y%m%d_%H%M%S)"
PADRAO_PROJETO='(python|\.py|sistema|checklist|guincho|rfid|liberar[ _-]*gt)'
PADRAO_COMANDO="^(Exec=.*|@.*)$PADRAO_PROJETO"

chmod +x "$LAUNCHER"
mkdir -p "$AUTOSTART_DIR"

backup_e_mover() {
    arquivo="$1"
    mkdir -p "$BACKUP_DIR"
    cp -p "$arquivo" "$BACKUP_DIR/$(basename "$arquivo")"
    rm -f "$arquivo"
    printf '%s\n' "Entrada antiga desativada (backup): $arquivo"
}

# Remove somente autostarts de projetos/programas Python identificáveis.
# Arquivos são preservados no diretório de backup para restauração manual.
for arquivo in "$AUTOSTART_DIR"/*.desktop; do
    [ -f "$arquivo" ] || continue
    [ "$arquivo" = "$DESKTOP_FILE" ] && continue
    if grep -Eiq "$PADRAO_COMANDO" "$arquivo"; then
        backup_e_mover "$arquivo"
    fi
done

# Em Raspberry Pi OS com LXDE, esta lista pode iniciar programas antes do
# diretório XDG. Se existir, ela será usada como única entrada do projeto.
if [ -f "$LXDE_AUTOSTART" ]; then
    mkdir -p "$BACKUP_DIR"
    cp -p "$LXDE_AUTOSTART" "$BACKUP_DIR/autostart.LXDE-pi"
    tmp_file=$(mktemp)
    grep -Eiv "$PADRAO_COMANDO" "$LXDE_AUTOSTART" > "$tmp_file" || true
    printf '@%s\n' "$LAUNCHER" >> "$tmp_file"
    mv "$tmp_file" "$LXDE_AUTOSTART"
    rm -f "$DESKTOP_FILE"
    printf '%s\n' "Autostart LXDE configurado: $LXDE_AUTOSTART"
else
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
    printf '%s\n' "Autostart XDG configurado: $DESKTOP_FILE"
fi

# Apenas informa se ainda existe uma entrada antiga em nível de sistema.
for arquivo in /etc/xdg/autostart/*.desktop /etc/xdg/lxsession/LXDE-pi/autostart; do
    [ -f "$arquivo" ] || continue
    if grep -Eiq "$PADRAO_COMANDO" "$arquivo"; then
        printf '%s\n' "ATENÇÃO: possível autostart antigo em nível de sistema: $arquivo"
        printf '%s\n' "Revise esse arquivo com sudo se outro projeto continuar abrindo."
    fi
done

if [ -d "$BACKUP_DIR" ]; then
    printf '%s\n' "Backups das entradas antigas: $BACKUP_DIR"
fi
printf '%s\n' "O projeto atual será iniciado no próximo login gráfico."
printf '%s\n' "Para aplicar: sudo reboot"
