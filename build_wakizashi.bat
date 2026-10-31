@echo off
echo === Сборка WakizashiRGB ===
pyinstaller --clean --noconfirm WakizashiRGB.spec
if %errorlevel% equ 0 (
    echo === Готово: dist\WakizashiRGB_v1.7.exe ===
) else (
    echo === Ошибка сборки! ===
)
pause
