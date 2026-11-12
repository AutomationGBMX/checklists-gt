@echo off
REM Inicia o dashboard e abre o navegador. Feche esta janela para parar.
REM
REM O dashboard lê os dados de uma CÓPIA DEDICADA do repositório (só leitura),
REM separada da pasta onde se edita o código. Assim o "git pull" automático
REM nunca esbarra em alterações locais.
cd /d "%~dp0"
set "CHECKLISTS_REPO=%~dp0..\..\checklists-gt-dados"

if not exist "%CHECKLISTS_REPO%\.git" (
    echo Criando a copia dedicada do repositorio em %CHECKLISTS_REPO% ...
    git clone -c core.autocrlf=false https://github.com/AutomationGBMX/checklists-gt.git "%CHECKLISTS_REPO%"
    if errorlevel 1 (
        echo Falha ao clonar. Verifique internet e credenciais do GitHub.
        pause
        exit /b 1
    )
)

start "" http://localhost:8501
python -m streamlit run app.py --server.headless true --browser.gatherUsageStats false
