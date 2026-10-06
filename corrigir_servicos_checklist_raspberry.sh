#!/bin/sh
set -u

SERVICOS_DUPLICADOS="checklist-gt-fullscreen.service checklist-gt.service myscript.service rainplant_v4.service"

printf '%s\n' 'Desativando serviços antigos e duplicados...'

for servico in $SERVICOS_DUPLICADOS; do
    sudo systemctl disable --now "$servico" 2>/dev/null || true
    sudo systemctl mask "$servico" 2>/dev/null || true
    printf '%s\n' "Bloqueado: $servico"
done

sudo systemctl daemon-reload

# Encerra processos antigos que tenham permanecido fora do controle do systemd.
sudo pkill -f '/home/alex/projects/rainplantrasp/main.py' 2>/dev/null || true
sudo pkill -f '/home/alex/projects/rainplant_v4/main.py' 2>/dev/null || true

printf '%s\n' ''
printf '%s\n' 'Serviços relacionados desativados/bloqueados.'
printf '%s\n' 'O sistema deverá iniciar somente pelo arquivo:'
printf '%s\n' '  ~/.config/autostart/sistema-gt-rfid.desktop'
printf '%s\n' ''
printf '%s\n' 'Verifique antes de reiniciar:'
printf '%s\n' '  systemctl is-enabled checklist-gt.service checklist-gt-fullscreen.service'
printf '%s\n' '  grep Exec ~/.config/autostart/sistema-gt-rfid.desktop'
printf '%s\n' ''
printf '%s\n' 'Depois reinicie com: sudo reboot'
printf '%s\n' ''
printf '%s\n' 'Para desfazer o bloqueio de um serviço: sudo systemctl unmask NOME.service'
