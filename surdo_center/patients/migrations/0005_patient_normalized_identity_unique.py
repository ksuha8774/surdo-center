from django.db import migrations


CREATE_NORMALIZE_NAME_FUNCTION = r"""
CREATE FUNCTION patients_normalize_name(value text)
RETURNS text
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
AS $$
    SELECT lower(btrim(regexp_replace(coalesce(value, ''), '[[:space:]]+', ' ', 'g')))
$$;
"""

CREATE_NORMALIZE_PHONE_FUNCTION = r"""
CREATE FUNCTION patients_normalize_phone(value text)
RETURNS text
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
AS $$
    SELECT CASE
        WHEN normalized.raw_value !~ '^\+?[0-9[:space:]()\-]+$' THEN NULL
        WHEN normalized.raw_value LIKE '+%'
             AND length(normalized.digits) BETWEEN 8 AND 15
             AND left(normalized.digits, 1) <> '0'
             AND (left(normalized.digits, 1) <> '7' OR length(normalized.digits) = 11)
            THEN '+' || normalized.digits
        WHEN normalized.raw_value NOT LIKE '+%' AND length(normalized.digits) = 10
            THEN '+7' || normalized.digits
        WHEN normalized.raw_value NOT LIKE '+%'
             AND length(normalized.digits) = 11
             AND left(normalized.digits, 1) IN ('7', '8')
            THEN '+7' || substring(normalized.digits FROM 2)
        ELSE NULL
    END
    FROM (
        SELECT
            btrim(regexp_replace(coalesce(value, ''), '[[:space:]]+', ' ', 'g')) AS raw_value,
            regexp_replace(coalesce(value, ''), '[^0-9]', '', 'g') AS digits
    ) AS normalized
$$;
"""


def assert_normalized_patient_data(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT array_agg(id ORDER BY id)
            FROM patients_patient
            GROUP BY
                patients_normalize_name(last_name),
                patients_normalize_name(first_name),
                patients_normalize_name(middle_name),
                birth_date,
                patients_normalize_phone(phone)
            HAVING count(*) > 1
            """
        )
        duplicate_groups = cursor.fetchall()
        if duplicate_groups:
            raise RuntimeError(
                "Нельзя создать уникальный индекс пациентов: найдены полные дубли "
                f"{[group[0] for group in duplicate_groups]}."
            )

        cursor.execute(
            "SELECT array_agg(id ORDER BY id) FROM patients_patient "
            "WHERE patients_normalize_phone(phone) IS NULL"
        )
        invalid_phone_ids = cursor.fetchone()[0]
        if invalid_phone_ids:
            raise RuntimeError(
                "Нельзя создать ограничение телефона: найдены неподдерживаемые номера у пациентов "
                f"{invalid_phone_ids}."
            )


class Migration(migrations.Migration):
    dependencies = [
        ("patients", "0004_alter_patient_city_alter_patient_house_and_more"),
    ]

    operations = [
        migrations.RunSQL(
            sql=CREATE_NORMALIZE_NAME_FUNCTION,
            reverse_sql="DROP FUNCTION patients_normalize_name(text);",
        ),
        migrations.RunSQL(
            sql=CREATE_NORMALIZE_PHONE_FUNCTION,
            reverse_sql="DROP FUNCTION patients_normalize_phone(text);",
        ),
        migrations.RunPython(assert_normalized_patient_data, migrations.RunPython.noop),
        migrations.RunSQL(
            sql=(
                "ALTER TABLE patients_patient "
                "ADD CONSTRAINT patients_patient_phone_normalized_valid "
                "CHECK (patients_normalize_phone(phone) IS NOT NULL);"
            ),
            reverse_sql=(
                "ALTER TABLE patients_patient "
                "DROP CONSTRAINT patients_patient_phone_normalized_valid;"
            ),
        ),
        migrations.RunSQL(
            sql="""
                CREATE UNIQUE INDEX patients_patient_normalized_identity_uniq
                ON patients_patient (
                    patients_normalize_name(last_name),
                    patients_normalize_name(first_name),
                    patients_normalize_name(middle_name),
                    birth_date,
                    patients_normalize_phone(phone)
                );
            """,
            reverse_sql="DROP INDEX patients_patient_normalized_identity_uniq;",
        ),
    ]
