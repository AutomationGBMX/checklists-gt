@echo off
cd /d "%~dp0"
set "CHECKLISTS_REPO=%~dp0..\..\checklists-gt-dados"

if not exist "%CHECKLISTS_REPO%\.git" (
    git clone -c core.autocrlf=false https://github.com/AutomationGBMX/checklists-gt.git "%CHECKLISTS_REPO%" || (pause & exit /b 1)
)

start "" http://localhost:8501
python -m streamlit run app.py
