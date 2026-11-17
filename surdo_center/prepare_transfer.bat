@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"
title ЮНА — подготовка переноса

echo.
echo ================================================
echo   Подготовка базы ЮНА для переноса
echo ================================================
echo.

if not exist ".env" (
    echo ОШИБКА: файл .env не найден. Сначала запустите проект на старом компьютере.
    pause
    exit /b 1
)

for /f "usebackq eol=# tokens=1,* delims==" %%A in (".env") do (
    if /I "%%A"=="POSTGRES_DB" set "DB_NAME=%%B"
    if /I "%%A"=="POSTGRES_USER" set "DB_USER=%%B"
    if /I "%%A"=="POSTGRES_PASSWORD" set "DB_PASSWORD=%%B"
    if /I "%%A"=="POSTGRES_HOST" set "DB_HOST=%%B"
    if /I "%%A"=="POSTGRES_PORT" set "DB_PORT=%%B"
)

set "PG_DUMP_EXE="
for /f "delims=" %%P in ('where pg_dump.exe 2^>nul') do if not defined PG_DUMP_EXE set "PG_DUMP_EXE=%%P"
if not defined PG_DUMP_EXE (
    for /d %%D in ("C:\Program Files\PostgreSQL\*") do if exist "%%~fD\bin\pg_dump.exe" set "PG_DUMP_EXE=%%~fD\bin\pg_dump.exe"
)
if not defined PG_DUMP_EXE (
    echo ОШИБКА: pg_dump.exe не найден. Установите PostgreSQL с Command Line Tools.
    pause
    exit /b 1
)

if /I "%~1"=="--check" (
    echo Проверка сценария подготовки переноса завершена успешно.
    exit /b 0
)

if not exist ".transfer" mkdir ".transfer"
set "PGPASSWORD=%DB_PASSWORD%"
echo Создание резервной копии текущей базы...
"%PG_DUMP_EXE%" --format=custom --no-owner --no-privileges --host="%DB_HOST%" --port="%DB_PORT%" --username="%DB_USER%" --dbname="%DB_NAME%" --file=".transfer\surdo_center.backup"
set "PGPASSWORD="
if errorlevel 1 goto :failed

copy /Y ".env" ".transfer\env.from.old.pc" >nul
echo.
echo Готово: создана папка .transfer.
echo Скопируйте на новый ноутбук всю папку проекта вместе с .transfer,
echo затем запустите deploy_new_laptop.bat.
pause
exit /b 0

:failed
echo.
echo ОШИБКА: резервную копию создать не удалось.
pause
exit /b 1
