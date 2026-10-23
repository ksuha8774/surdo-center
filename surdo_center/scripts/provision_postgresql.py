from getpass import getpass
from pathlib import Path
import sys

import psycopg
from psycopg import sql
from dotenv import dotenv_values


PROJECT_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_DIR / ".env"


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
        sys.stderr.reconfigure(errors="replace")

    config = dotenv_values(ENV_FILE)
    required = ("POSTGRES_DB", "POSTGRES_USER", "POSTGRES_PASSWORD", "POSTGRES_HOST", "POSTGRES_PORT")
    missing = [name for name in required if not config.get(name)]
    if missing:
        print(f"ОШИБКА: в .env не заполнены: {', '.join(missing)}.")
        return 1

    admin_user = input("Администратор PostgreSQL [postgres]: ").strip() or "postgres"
    admin_password = getpass("Пароль администратора PostgreSQL: ")
    if not admin_password:
        print("ОШИБКА: пароль не может быть пустым.")
        return 1

    try:
        connection = psycopg.connect(
            dbname="postgres",
            user=admin_user,
            password=admin_password,
            host=config["POSTGRES_HOST"],
            port=config["POSTGRES_PORT"],
            connect_timeout=5,
            autocommit=True,
        )
        with connection:
            role_exists = connection.execute(
                "SELECT 1 FROM pg_roles WHERE rolname = %s", (config["POSTGRES_USER"],)
            ).fetchone()
            role_identifier = sql.Identifier(config["POSTGRES_USER"])
            password_literal = sql.Literal(config["POSTGRES_PASSWORD"])
            if role_exists:
                connection.execute(
                    sql.SQL("ALTER ROLE {} WITH LOGIN PASSWORD {} CREATEDB").format(
                        role_identifier, password_literal
                    )
                )
            else:
                connection.execute(
                    sql.SQL("CREATE ROLE {} WITH LOGIN PASSWORD {} CREATEDB").format(
                        role_identifier, password_literal
                    )
                )

            database_exists = connection.execute(
                "SELECT 1 FROM pg_database WHERE datname = %s", (config["POSTGRES_DB"],)
            ).fetchone()
            database_identifier = sql.Identifier(config["POSTGRES_DB"])
            if database_exists:
                connection.execute(
                    sql.SQL("ALTER DATABASE {} OWNER TO {}").format(database_identifier, role_identifier)
                )
            else:
                connection.execute(
                    sql.SQL("CREATE DATABASE {} OWNER {} ENCODING 'UTF8' TEMPLATE template0").format(
                        database_identifier, role_identifier
                    )
                )
    except psycopg.Error as error:
        print("ОШИБКА: создать роль или базу PostgreSQL не удалось.")
        print(f"Причина: {error}")
        return 1

    print(f"База {config['POSTGRES_DB']} и роль {config['POSTGRES_USER']} готовы к работе.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
