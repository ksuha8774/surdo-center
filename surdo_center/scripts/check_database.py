from pathlib import Path
import sys

import psycopg
from dotenv import dotenv_values


PROJECT_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_DIR / ".env"


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
        sys.stderr.reconfigure(errors="replace")

    if not ENV_FILE.exists():
        print("ОШИБКА: отсутствует файл .env с настройками проекта.")
        return 1

    config = dotenv_values(ENV_FILE)
    required = ("POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_HOST", "POSTGRES_PORT")
    missing = [name for name in required if not config.get(name)]
    if missing:
        print(f"ОШИБКА: в .env не заполнены: {', '.join(missing)}.")
        return 1

    try:
        with psycopg.connect(
            dbname=config["POSTGRES_DB"],
            user=config["POSTGRES_USER"],
            password=config["POSTGRES_PASSWORD"],
            host=config["POSTGRES_HOST"],
            port=config["POSTGRES_PORT"],
            connect_timeout=5,
        ) as connection:
            connection.execute("SELECT 1")
    except psycopg.Error as error:
        print("ОШИБКА: приложение не может подключиться к PostgreSQL.")
        print(f"Причина: {error}")
        return 1

    print("Подключение к PostgreSQL установлено.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
