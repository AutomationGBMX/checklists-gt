#!/bin/sh
set -eu

PROJETO_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
LAUNCHER="$PROJETO_DIR/iniciar_sistema_gt.sh"
REAL_USER="${SUDO_USER:-$(id -un)}"
if [ "$(id -u)" -eq 0 ] && [ -n "${SUDO_USER:-}" ]; then
    REAL_HOME=$(getent passwd "$REAL_USER" | cut -d: -f6)
else
    REAL_USER=$(id -un)
    REAL_HOME="$HOME"
fi
[ -n "$REAL_HOME" ] || REAL_HOME="$HOME"

AUTOSTART_DIR="$REAL_HOME/.config/autostart"
DESKTOP_FILE="$AUTOSTART_DIR/sistema-gt-rfid.desktop"
LXDE_AUTOSTART="$REAL_HOME/.config/lxsession/LXDE-pi/autostart"
BACKUP_DIR="$REAL_HOME/.config/sistema-gt-autostart-backup-$(date +%Y%m%d_%H%M%S)"
PADRAO_EXEC='^Exec=.*(python|\.py|/home|/opt|sistema|checklist|guincho|rfid|liberar[ _-]*gt)'
PADRAO_LXDE='^@.*(python|\.py|/home|/opt|sistema|checklist|guincho|rfid|liberar[ _-]*gt)'

if [ "$(id -u)" -eq 0 ]; then
    PODE_ALTERAR_SISTEMA=1
else
    PODE_ALTERAR_SISTEMA=0
fi

backup_arquivo() {
    arquivo="$1"
    nome=$(printf '%s' "$arquivo" | sed 's#^/##; s#/#_#g')
    mkdir -p "$BACKUP_DIR"
    cp -p "$arquivo" "$BACKUP_DIR/$nome"
}

remover_desktop_usuario() {
    arquivo="$1"
    [ "$arquivo" = "$DESKTOP_FILE" ] && return 0
    if grep -Eiq "$PADRAO_EXEC" "$arquivo"; then
        backup_arquivo "$arquivo"
        rm -f "$arquivo"
        printf '%s\n' "Desativado autostart antigo: $arquivo"
    fi
}

# Garante que o diretório do projeto seja o diretório de trabalho do programa.
chmod +x "$LAUNCHER"
mkdir -p "$AUTOSTART_DIR"

# Remove entradas antigas do autostart do usuário, mantendo backup.
for arquivo in "$AUTOSTART_DIR"/*.desktop; do
    [ -f "$arquivo" ] || continue
    remover_desktop_usuario "$arquivo"
done

# Se o Raspberry usa LXDE, essa configuração tem prioridade sobre o XDG.
# Mantém as linhas normais do LXDE e remove apenas comandos de projetos.
if [ -f "$LXDE_AUTOSTART" ]; then
    backup_arquivo "$LXDE_AUTOSTART"
    tmp_file=$(mktemp)
    grep -Eiv "$PADRAO_LXDE" "$LXDE_AUTOSTART" > "$tmp_file" || true
    printf '@%s\n' "$LAUNCHER" >> "$tmp_file"
    mv "$tmp_file" "$LXDE_AUTOSTART"
    rm -f "$DESKTOP_FILE"
    printf '%s\n' "Checklist definido como autostart LXDE: $LXDE_AUTOSTART"
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
    printf '%s\n' "Checklist definido como autostart XDG: $DESKTOP_FILE"
fi

# Quando executado com sudo, substitui também entradas antigas do sistema.
if [ "$PODE_ALTERAR_SISTEMA" -eq 1 ]; then
    for arquivo in /etc/xdg/autostart/*.desktop; do
        [ -f "$arquivo" ] || continue
        if grep -Eiq "$PADRAO_EXEC" "$arquivo" && ! grep -Fq "$LAUNCHER" "$arquivo"; then
            backup_arquivo "$arquivo"
            rm -f "$arquivo"
            printf '%s\n' "Desativado autostart antigo do sistema: $arquivo"
        fi
    done

    for arquivo in /etc/xdg/lxsession/*/autostart; do
        [ -f "$arquivo" ] || continue
        if grep -Eiq "$PADRAO_LXDE" "$arquivo"; then
            backup_arquivo "$arquivo"
            tmp_file=$(mktemp)
            grep -Eiv "$PADRAO_LXDE" "$arquivo" > "$tmp_file" || true
            mv "$tmp_file" "$arquivo"
            printf '%s\n' "Removido comando antigo do sistema: $arquivo"
        fi
    done
else
    # Sem sudo, apenas informa se ainda há candidato em nível de sistema.
    for arquivo in /etc/xdg/autostart/*.desktop /etc/xdg/lxsession/*/autostart; do
        [ -f "$arquivo" ] || continue
        if grep -Eiq "$PADRAO_EXEC|$PADRAO_LXDE" "$arquivo"; then
            printf '%s\n' "ATENÇÃO: entrada antiga em nível de sistema: $arquivo"
            printf '%s\n' "Execute este instalador novamente com sudo para desativá-la."
        fi
    done
fi

if [ -d "$BACKUP_DIR" ]; then
    if [ "$(id -u)" -eq 0 ]; then
        GRUPO_USUARIO=$(id -gn "$REAL_USER" 2>/dev/null || printf '%s' "$REAL_USER")
        chown -R "$REAL_USER:$GRUPO_USUARIO" "$BACKUP_DIR" 2>/dev/null || true
    fi
    printf '%s\n' "Backup das configurações antigas: $BACKUP_DIR"
fi

printf '%s\n' "Inicialização configurada exclusivamente para o checklist."
printf '%s\n' "Reinicie com: sudo reboot"
