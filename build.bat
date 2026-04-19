@echo off
echo Building Spectrorama...
python -m PyInstaller spectrorama.spec --clean
echo Done. Output: dist\Spectrorama.exe
