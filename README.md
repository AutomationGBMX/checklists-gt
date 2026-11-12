# Checklists GT — GBMX

## Estrutura

| Pasta | Conteúdo |
|---|---|
| raiz (`sistema_gt_rfid_V33.py`, `*.sh`) | Raspberry Pi |
| `nucleo/` | Lógica compartilhada |
| `dashboard/` | Painel web |
| `programa_gbmx/` | GUI Windows |
| `ferramentas/` | Scripts auxiliares |

## Instalar em outra máquina (Windows)

Copiar `PainelGBMX.exe` para qualquer pasta e abrir. Não precisa de Git, Docker nem Python:
o programa baixa os checklists do GitHub sozinho e guarda uma cópia em `%LOCALAPPDATA%\PainelGBMX`
(sem internet, mostra os últimos dados baixados).

Na primeira execução é criado `painel_gbmx.ini` ao lado do .exe:
- `GITHUB_TOKEN=`: token somente leitura, só se o repositório for privado.
- `INTERVALO_SEGUNDOS=30`: intervalo de verificação.

Gerar o .exe: `programa_gbmx\gerar_exe.bat`.

## Painel web (Docker)

1. Instalar **Git** e **Docker Desktop**.
2. Baixar o projeto:
   ```powershell
   git clone https://github.com/AutomationGBMX/checklists-gt.git C:\GBMX\checklists-gt
   cd C:\GBMX\checklists-gt
   copy .env.example .env
   ```
   Repositório privado: colar um token somente leitura em `GITHUB_TOKEN=` no `.env`.
3. `docker compose up -d --build` (atualizar: `git pull` e o mesmo comando).
