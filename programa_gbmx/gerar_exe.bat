@echo off
cd /d "%~dp0"

python -m pip install --quiet -r requirements.txt || goto erro
python gerar_icone.py || goto erro
python -m PyInstaller --noconfirm --clean --onefile --windowed ^
    --name PainelGBMX --icon "%~dp0assets\icone.ico" ^
    --distpath dist --workpath build --specpath build ^
    --paths .. --add-data "%~dp0web;web" ^
    --exclude-module PyQt5 --exclude-module PySide6 --exclude-module PySide2 ^
    --exclude-module gi --exclude-module matplotlib --exclude-module pandas ^
    --exclude-module numpy --exclude-module tkinter --exclude-module streamlit ^
    --exclude-module altair --exclude-module pyarrow --exclude-module PIL ^
    painel_standalone.py || goto erro

copy /y dist\PainelGBMX.exe ..\PainelGBMX.exe >nul || goto erro
echo Pronto: PainelGBMX.exe
pause
exit /b 0

:erro
echo FALHA ao gerar o executavel (feche o PainelGBMX.exe se estiver aberto).
pause
exit /b 1
