# Checklists GT — GBMX

## Estrutura

| Pasta | Conteúdo |
|---|---|
| raiz (`sistema_gt_rfid_V33.py`, `*.sh`) | Raspberry Pi |
| `nucleo/` | Lógica compartilhada |
| `dashboard/` | Painel web |
| `programa_gbmx/` | Aplicativo Windows |
| `ferramentas/` | Scripts auxiliares |

## Instalar em outra máquina (Windows)

1. Instalar **Git** e **Docker Desktop** (em *Settings → General*, marcar "Start Docker Desktop when you sign in").
2. Baixar o projeto:
   ```powershell
   git clone https://github.com/AutomationGBMX/checklists-gt.git C:\GBMX\checklists-gt
   cd C:\GBMX\checklists-gt
   copy .env.example .env
   ```
   Repositório privado: colar um token somente leitura em `GITHUB_TOKEN=` no `.env`.
3. Abrir `PainelGBMX.exe` (a primeira vez leva alguns minutos).

## Atualizar

```powershell
git pull
docker compose up -d --build
```
