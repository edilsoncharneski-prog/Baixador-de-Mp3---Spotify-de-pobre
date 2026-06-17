@echo off
setlocal

set COMMIT_MSG=%*
if "%COMMIT_MSG%"=="" set COMMIT_MSG=Atualiza projeto

git status
git add .gitignore README.md requirements.txt main.py main_gui.py core atualizar_github.bat
git commit -m "%COMMIT_MSG%"
git push origin main

pause
