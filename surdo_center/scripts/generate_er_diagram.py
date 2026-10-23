"""Generate an editable diagrams.net ER diagram from the current Django models."""

import html
import os
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()

from django.apps import apps


OUTPUT = Path(__file__).resolve().parents[2] / "ER_диаграмма_АСУ_сурдологического_центра_актуальная.drawio"

BUSINESS_MODELS = (
    "accounts.User",
    "accounts.Doctor",
    "patients.Patient",
    "scheduling.DoctorScheduleTemplate",
    "scheduling.DoctorScheduleException",
    "scheduling.Appointment",
    "medical.MedicalVisit",
    "billing.Service",
    "billing.ProvidedService",
    "billing.Payment",
    "audiometry.AudiometryExam",
    "audiometry.AudiometryMeasurement",
    "audiometry.AudiometryCalculation",
    "integrations.ExternalSystem",
    "integrations.DoctorExternalMapping",
    "integrations.ServiceExternalMapping",
    "integrations.ExternalBookingRequest",
    "integrations.SyncEvent",
)

SYSTEM_MODELS = (
    "accounts.User",
    "auth.Group",
    "auth.Permission",
    "contenttypes.ContentType",
    "admin.LogEntry",
    "sessions.Session",
)

DSS_TABLES = {
    "dss_rule_sets": [
        "PK rule_set_id : bigint", "UQ code : varchar(50)", "UQ version : varchar(30)",
        "name : varchar(150)", "effective_from : date", "effective_to : date NULL",
        "is_active : boolean", "created_at : timestamptz",
    ],
    "dss_rules": [
        "PK rule_id : bigint", "FK rule_set_id : bigint", "UQ rule_code : varchar(50)",
        "name : varchar(180)", "priority : integer", "conclusion_template : text NULL",
        "recommendation_template : text NULL", "is_active : boolean", "created_at : timestamptz",
        "match_mode : varchar(3)",
    ],
    "dss_rule_conditions": [
        "PK condition_id : bigint", "FK rule_id : bigint", "parameter_code : varchar(50)",
        "comparison_operator : varchar(10)", "comparison_value : numeric(10,2)", "sequence_no : smallint",
    ],
    "dss_assessments": [
        "PK assessment_id : bigint", "FK exam_id : bigint", "FK rule_set_id : bigint",
        "FK reviewed_by : bigint NULL", "status : varchar(20)", "preliminary_conclusion : text",
        "preliminary_recommendation : text", "doctor_comment : text NULL", "created_at : timestamptz",
        "reviewed_at : timestamptz NULL",
    ],
    "dss_rule_activations": [
        "PK activation_id : bigint", "FK assessment_id : bigint", "FK rule_id : bigint",
        "output_conclusion : text NULL", "output_recommendation : text NULL", "created_at : timestamptz",
    ],
    "dss_activation_details": [
        "PK activation_detail_id : bigint", "FK activation_id : bigint", "FK condition_id : bigint",
        "actual_value : numeric(10,2)", "condition_met : boolean",
    ],
}

DSS_RELATIONS = (
    ("dss_rules", "dss_rule_sets", "rule_set_id"),
    ("dss_rule_conditions", "dss_rules", "rule_id"),
    ("dss_assessments", "dss_rule_sets", "rule_set_id"),
    ("dss_rule_activations", "dss_assessments", "assessment_id"),
    ("dss_rule_activations", "dss_rules", "rule_id"),
    ("dss_activation_details", "dss_rule_activations", "activation_id"),
    ("dss_activation_details", "dss_rule_conditions", "condition_id"),
)


def field_type(field):
    internal = field.get_internal_type()
    if internal in {"BigAutoField", "BigIntegerField", "OneToOneField", "ForeignKey"}:
        return "bigint"
    if internal == "AutoField":
        return "integer"
    if internal in {"PositiveSmallIntegerField", "SmallIntegerField"}:
        return "smallint"
    if internal in {"PositiveIntegerField", "IntegerField"}:
        return "integer"
    if internal in {"CharField", "EmailField"}:
        return f"varchar({field.max_length})"
    if internal == "TextField":
        return "text"
    if internal == "DateTimeField":
        return "timestamptz"
    if internal == "DateField":
        return "date"
    if internal == "TimeField":
        return "time"
    if internal == "BooleanField":
        return "boolean"
    if internal == "DecimalField":
        return f"numeric({field.max_digits},{field.decimal_places})"
    if internal == "UUIDField":
        return "uuid"
    if internal == "JSONField":
        return "jsonb"
    return internal


def model_table(model):
    rows = []
    relations = []
    for field in model._meta.local_fields:
        keys = []
        if field.primary_key:
            keys.append("PK")
        if field.is_relation:
            keys.append("FK")
            relations.append((model._meta.db_table, field.related_model._meta.db_table, field.column))
        if field.unique and not field.primary_key:
            keys.append("UQ")
        prefix = ("/".join(keys) + " ") if keys else ""
        nullable = " NULL" if field.null else ""
        rows.append(f"{prefix}{field.column} : {field_type(field)}{nullable}")
    for constraint in model._meta.constraints:
        kind = "UQ" if constraint.__class__.__name__ in {"UniqueConstraint", "ExclusionConstraint"} else "CK"
        rows.append(f"{kind} {constraint.name}")
    return model._meta.db_table, rows, relations


def system_tables():
    result = []
    relations = []
    seen = set()
    for label in SYSTEM_MODELS:
        table, rows, links = model_table(apps.get_model(label))
        if table not in seen:
            result.append((table, rows))
            relations.extend(links)
            seen.add(table)

    user = apps.get_model("accounts.User")
    group = apps.get_model("auth.Group")
    for through in (user.groups.through, user.user_permissions.through, group.permissions.through):
        table, rows, links = model_table(through)
        if table not in seen:
            result.append((table, rows))
            relations.extend(links)
            seen.add(table)

    result.append(("django_migrations", [
        "PK id : bigint", "app : varchar(255)", "name : varchar(255)", "applied : timestamptz",
    ]))
    return result, relations


def add_page(mxfile, name, title, tables, relations, note=None, colors=("#EAF3F8", "#6C8EBF")):
    diagram = ET.SubElement(mxfile, "diagram", {"name": name, "id": name.replace(" ", "_")})
    graph = ET.SubElement(diagram, "mxGraphModel", {
        "dx": "1800", "dy": "1200", "grid": "1", "gridSize": "10", "guides": "1",
        "tooltips": "1", "connect": "1", "arrows": "1", "fold": "1", "page": "1",
        "pageScale": "1", "pageWidth": "3600", "pageHeight": "2600", "math": "0", "shadow": "0",
    })
    root = ET.SubElement(graph, "root")
    ET.SubElement(root, "mxCell", {"id": "0"})
    ET.SubElement(root, "mxCell", {"id": "1", "parent": "0"})

    title_cell = ET.SubElement(root, "mxCell", {
        "id": "title", "parent": "1", "vertex": "1", "value": f"<b>{html.escape(title)}</b>",
        "style": "text;html=1;align=center;verticalAlign=middle;fontSize=26;fontColor=#163247;",
    })
    ET.SubElement(title_cell, "mxGeometry", {"x": "600", "y": "20", "width": "2200", "height": "45", "as": "geometry"})

    if note:
        note_cell = ET.SubElement(root, "mxCell", {
            "id": "note", "parent": "1", "vertex": "1", "value": html.escape(note),
            "style": "rounded=1;whiteSpace=wrap;html=1;fillColor=#FFF2CC;strokeColor=#D6B656;fontSize=15;align=left;spacing=8;",
        })
        ET.SubElement(note_cell, "mxGeometry", {"x": "80", "y": "80", "width": "3200", "height": "58", "as": "geometry"})
        top = 170
    else:
        top = 90

    columns = [top, top, top]
    ids = {}
    for index, (table_name, rows) in enumerate(tables):
        column = min(range(3), key=lambda item: columns[item])
        x = 70 + column * 1120
        y = columns[column]
        height = 52 + len(rows) * 22
        cell_id = f"table_{index}"
        ids[table_name] = cell_id
        label_rows = "<br>".join(html.escape(row) for row in rows)
        label = f"<div style='font-size:17px;text-align:center'><b>{html.escape(table_name)}</b></div><hr><div style='font-family:Consolas;font-size:13px;line-height:1.45'>{label_rows}</div>"
        cell = ET.SubElement(root, "mxCell", {
            "id": cell_id, "parent": "1", "vertex": "1", "value": label,
            "style": f"rounded=0;whiteSpace=wrap;html=1;fillColor={colors[0]};strokeColor={colors[1]};align=left;verticalAlign=top;spacing=10;fontSize=13;",
        })
        ET.SubElement(cell, "mxGeometry", {"x": str(x), "y": str(y), "width": "980", "height": str(height), "as": "geometry"})
        columns[column] += height + 70

    edge_index = 0
    for source, target, label in relations:
        if source not in ids or target not in ids:
            continue
        edge = ET.SubElement(root, "mxCell", {
            "id": f"edge_{edge_index}", "parent": "1", "edge": "1",
            "source": ids[source], "target": ids[target], "value": html.escape(label),
            "style": "edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;startArrow=ERmany;endArrow=ERone;fontSize=12;",
        })
        ET.SubElement(edge, "mxGeometry", {"relative": "1", "as": "geometry"})
        edge_index += 1


def main():
    business_tables = []
    business_relations = []
    for label in BUSINESS_MODELS:
        table, rows, links = model_table(apps.get_model(label))
        business_tables.append((table, rows))
        business_relations.extend(links)

    framework_tables, framework_relations = system_tables()
    dss_tables = list(DSS_TABLES.items())

    mxfile = ET.Element("mxfile", {"host": "app.diagrams.net", "agent": "Codex", "compressed": "false"})
    add_page(
        mxfile,
        "1 Фактическая предметная модель",
        "ER-диаграмма АСУ сурдологического центра — фактические Django-модели",
        business_tables,
        business_relations,
        "Сформировано из текущего состояния Django ORM. Рабочая PostgreSQL не мигрировалась.",
    )
    add_page(
        mxfile,
        "2 Служебные таблицы Django",
        "Служебные таблицы Django Authentication и инфраструктуры",
        framework_tables,
        framework_relations,
        "Таблицы создаются штатными миграциями Django и показаны отдельно от предметной модели.",
        colors=("#F5F5F5", "#666666"),
    )
    add_page(
        mxfile,
        "3 СППР без изменений",
        "СППР — проектная ER-модель без изменений",
        dss_tables,
        DSS_RELATIONS,
        "Эти таблицы сохранены из исходной ER-модели, но пока не реализованы в Django и не создаются новыми миграциями.",
        colors=("#F8E7E7", "#B85450"),
    )

    ET.indent(mxfile, space="  ")
    OUTPUT.write_text('<?xml version="1.0" encoding="utf-8"?>\n' + ET.tostring(mxfile, encoding="unicode"), encoding="utf-8")
    print(OUTPUT)


if __name__ == "__main__":
    main()
