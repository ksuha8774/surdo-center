@echo off
chcp 65001 >nul
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
title ЮНА — развёртывание на новом ноутбуке

echo.
echo ================================================
echo   Развёртывание системы ЮНА
echo ================================================
echo.

set "PYTHON_READY="
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -c "import sys" >nul 2>&1
    if errorlevel 1 (
        echo Удаление нерабочего виртуального окружения со старого компьютера...
        rmdir /S /Q ".venv"
    ) else (
        set "PYTHON_READY=1"
    )
)
if not defined PYTHON_READY (
    py -3.12 --version >nul 2>&1
    if not errorlevel 1 set "PYTHON_READY=1"
)
if not defined PYTHON_READY (
    echo ОШИБКА: требуется Python 3.12 x64 с Python Launcher.
    echo Установите его с python.org и включите Add Python to PATH.
    pause
    exit /b 1
)

if not exist ".env" (
    if exist ".transfer\env.from.old.pc" (
        copy /Y ".transfer\env.from.old.pc" ".env" >nul
        echo Настройки .env перенесены со старого компьютера.
    ) else (
        echo Создание безопасных локальных настроек .env...
        powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\create_local_env.ps1" -OutputPath ".env"
        if errorlevel 1 goto :failed
    )
)

echo.
echo Подготовка окружения, PostgreSQL и схемы базы...
call start_surdo_center.bat --check
if errorlevel 1 goto :failed

if exist ".transfer\surdo_center.backup" (
    echo.
    echo Найдена резервная копия данных со старого компьютера.
    set "RESTORE_CHOICE="
    set /P "RESTORE_CHOICE=Восстановить её в новую базу? Введите ДА: "
    if /I "!RESTORE_CHOICE!"=="ДА" call :restore_backup
    if errorlevel 1 goto :failed
)

if /I "%~1"=="--check" (
    echo.
    echo Проверка сценария развёртывания завершена успешно.
    exit /b 0
)

echo.
echo Развёртывание завершено. Запуск приложения...
call start_surdo_center.bat
exit /b %errorlevel%

:restore_backup
for /f "usebackq eol=# tokens=1,* delims==" %%A in (".env") do (
    if /I "%%A"=="POSTGRES_DB" set "DB_NAME=%%B"
    if /I "%%A"=="POSTGRES_USER" set "DB_USER=%%B"
    if /I "%%A"=="POSTGRES_PASSWORD" set "DB_PASSWORD=%%B"
    if /I "%%A"=="POSTGRES_HOST" set "DB_HOST=%%B"
    if /I "%%A"=="POSTGRES_PORT" set "DB_PORT=%%B"
)
set "PG_RESTORE_EXE="
for /f "delims=" %%P in ('where pg_restore.exe 2^>nul') do if not defined PG_RESTORE_EXE set "PG_RESTORE_EXE=%%P"
if not defined PG_RESTORE_EXE (
    for /d %%D in ("C:\Program Files\PostgreSQL\*") do if exist "%%~fD\bin\pg_restore.exe" set "PG_RESTORE_EXE=%%~fD\bin\pg_restore.exe"
)
if not defined PG_RESTORE_EXE (
    echo ОШИБКА: pg_restore.exe не найден. Установите PostgreSQL с Command Line Tools.
    exit /b 1
)
set "PGPASSWORD=%DB_PASSWORD%"
echo Восстановление пользователей, пациентов и остальных данных...
"%PG_RESTORE_EXE%" --clean --if-exists --exit-on-error --no-owner --no-privileges --host="%DB_HOST%" --port="%DB_PORT%" --username="%DB_USER%" --dbname="%DB_NAME%" ".transfer\surdo_center.backup"
set "PGPASSWORD="
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" manage.py migrate --noinput
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" manage.py check
exit /b %errorlevel%

:failed
echo.
echo ОШИБКА: развёртывание не завершено. Исправьте сообщение выше и повторите запуск.
pause
exit /b 1
