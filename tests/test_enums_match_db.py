from sqlalchemy import Connection, text

from procedurescout_core.enums import DB_ENUMS


def test_python_enums_match_postgres(conn: Connection) -> None:
    rows = conn.execute(
        text(
            "SELECT n.nspname || '.' || t.typname, e.enumlabel "
            "FROM pg_type t JOIN pg_enum e ON e.enumtypid = t.oid "
            "JOIN pg_namespace n ON n.oid = t.typnamespace "
            "WHERE n.nspname IN ('ref', 'src', 'price') ORDER BY 1, e.enumsortorder"
        )
    )
    in_db: dict[str, list[str]] = {}
    for name, label in rows:
        in_db.setdefault(name, []).append(label)
    in_code = {name: [m.value for m in enum] for name, enum in DB_ENUMS.items()}
    assert in_db == in_code
