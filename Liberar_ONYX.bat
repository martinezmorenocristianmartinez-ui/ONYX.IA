@echo off
title Liberar Instancias de ONYX
echo.
echo ============================================================
echo   LIBERAR INSTANCIAS DE ONYX - RESET DE PROCESOS HUNG
echo ============================================================
echo.
echo Este script cerrara todos los procesos hung de Python para liberar el
echo mutex "ONYX_AI_SINGLE_INSTANCE_MUTEX" de la sesion de administrador.
echo.
echo Presione una tecla para continuar y forzar el cierre...
pause > nul
echo.
taskkill /F /IM python.exe
taskkill /F /IM pythonw.exe
echo.
echo ============================================================
echo   PROCESOS DEPURADOS CON EXITO. Ya puedes iniciar ONYX Beta.
echo ============================================================
echo.
pause
