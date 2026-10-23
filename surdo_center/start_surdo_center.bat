@echo off
chcp 65001 >nul
setlocal
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

cd /d "%~dp0"
title АудиоМед — запуск системы

set "VENV_DIR=%~dp0.venv"
set "PYTHON_EXE=%VENV_DIR%\Scripts\python.exe"

echo.
echo ================================================
echo   АудиоМед — АСУ сурдологического центра
echo ================================================
echo.

if not exist "%PYTHON_EXE%" (
    echo [1/7] Создание собственного виртуального окружения проекта...
    where py >nul 2>&1
    if not errorlevel 1 (
        py -3.12 -m venv "%VENV_DIR%"
    ) else (
        where python >nul 2>&1
        if errorlevel 1 goto :python_missing
        python -m venv "%VENV_DIR%"
    )
    if errorlevel 1 goto :failed
) else (
    echo [1/7] Собственное виртуальное окружение найдено.
)

:environment_ready

if not exist ".env" (
    copy /Y ".env.example" ".env" >nul
    echo.
    echo ОШИБКА: создан файл .env. Заполните в нём секреты и параметры PostgreSQL.
    pause
    exit /b 1
)

echo [2/7] Проверка зависимостей...
"%PYTHON_EXE%" -c "import django, psycopg, dotenv" >nul 2>&1
if errorlevel 1 (
    echo       Установка зависимостей...
    "%PYTHON_EXE%" -m pip install --disable-pip-version-check -r requirements.txt
    if errorlevel 1 goto :failed
) else (
    echo       Зависимости установлены.
)

echo [3/7] Проверка подключения к PostgreSQL...
"%PYTHON_EXE%" scripts\check_database.py
if errorlevel 1 (
    echo.
    echo Для первого запуска нужно создать отдельную роль и базу проекта.
    "%PYTHON_EXE%" scripts\provision_postgresql.py
    if errorlevel 1 goto :failed
    "%PYTHON_EXE%" scripts\check_database.py
    if errorlevel 1 goto :failed
)

echo [4/7] Применение миграций базы данных...
"%PYTHON_EXE%" manage.py migrate --noinput
if errorlevel 1 goto :failed

echo [5/7] Перенос сохранённого состояния начальной версии...
"%PYTHON_EXE%" manage.py restore_initial_state
if errorlevel 1 goto :failed

echo [6/7] Подготовка начальных справочников...
"%PYTHON_EXE%" manage.py initialize_system
if errorlevel 1 goto :failed

echo [7/7] Проверка конфигурации приложения...
"%PYTHON_EXE%" manage.py check
if errorlevel 1 goto :failed

if /I "%~1"=="--check" (
    echo Проверка запуска завершена успешно.
    exit /b 0
)

echo Запуск веб-приложения...
echo.
echo Адрес: http://127.0.0.1:8010/
echo Для остановки закройте окно сервера.
echo.

start "АудиоМед — сервер" "%PYTHON_EXE%" manage.py runserver 127.0.0.1:8010 --noreload --no-color
timeout /t 2 /nobreak >nul
start "" "http://127.0.0.1:8010/"
exit /b 0

:python_missing
echo.
echo ОШИБКА: Python не найден.
echo Установите Python 3.12 и повторите запуск.
pause
exit /b 1

:failed
echo.
echo ОШИБКА: запуск не завершён. Сообщение указано выше.
pause
exit /b 1
