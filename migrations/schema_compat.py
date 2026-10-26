"""Evita falsos diffs de FKs inline legadas, verificando a regra real no SQLite.

O inspector pode omitir ondelete nas declarações REFERENCES da versão sqlite3.
Só se omite uma operação quando PRAGMA confirma todos os alvos e ações do modelo.
Uma alteração real de ação, alvo ou coluna continua a ser devolvida ao Alembic.
"""

from sqlalchemy import Integer


def include_object(obj, name, type_, reflected, compare_to, *, connection, metadata):
    if (
        type_ == "column"
        and not reflected
        and compare_to is not None
        and obj.primary_key
        and isinstance(obj.type, Integer)
        and len(obj.table.primary_key.columns) == 1
        and connection.dialect.name == "sqlite"
        and compare_to.primary_key
    ):
        # INTEGER PRIMARY KEY é o ROWID gerado pelo SQLite; PRAGMA table_info
        # reporta nullable=True quando o DDL legado não escreveu NOT NULL.
        compare_to.nullable = obj.nullable
    if type_ != "foreign_key_constraint" or compare_to is not None:
        return True
    if connection.dialect.name != "sqlite" or obj.table.name not in metadata.tables:
        return True

    def signature(constraint):
        return [(element.parent.name, element.target_fullname) for element in constraint.elements]

    desired = next(
        (
            fk
            for fk in metadata.tables[obj.table.name].foreign_key_constraints
            if signature(fk) == signature(obj)
        ),
        None,
    )
    if (
        desired is None
        or desired.deferrable
        or desired.initially
        or desired.match
        or obj.deferrable
        or obj.initially
        or obj.match
    ):
        return True
    table = connection.dialect.identifier_preparer.quote(obj.table.name)
    rows = connection.exec_driver_sql(f"PRAGMA foreign_key_list({table})").mappings().all()
    groups = {}
    for row in rows:
        groups.setdefault(row["id"], []).append(row)
    for group in groups.values():
        group.sort(key=lambda row: row["seq"])
        actual = [(row["from"], f"{row['table']}.{row['to']}") for row in group]
        if actual == signature(desired):
            if (
                group[0]["on_delete"].upper() == (desired.ondelete or "NO ACTION").upper()
                and group[0]["on_update"].upper() == (desired.onupdate or "NO ACTION").upper()
            ):
                return False
    return True
