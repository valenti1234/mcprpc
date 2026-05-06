import os
from sqlmodel import create_engine, SQLModel, Session, select
from app.config import settings
from app.models import FunctionRecord
from app.repository import FunctionRepository

engine = create_engine(
    settings.DATABASE_URL, 
    echo=False,
    connect_args={
        "check_same_thread": False,
        "timeout": float(os.getenv("MCPRPC_SQLITE_TIMEOUT_S", "30")),
    },
)

def init_db():
    reset = os.getenv("MCPRPC_REGISTRY_RESET_DB_ON_START", "0").strip().lower() in ("1", "true", "yes")
    if reset:
        SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)
    with engine.begin() as conn:
        if conn.dialect.name != "sqlite":
            return
        conn.exec_driver_sql("PRAGMA journal_mode=WAL")
        conn.exec_driver_sql("PRAGMA synchronous=NORMAL")
        conn.exec_driver_sql(f"PRAGMA busy_timeout={int(float(os.getenv('MCPRPC_SQLITE_BUSY_TIMEOUT_MS', '5000')))}")
        rows = conn.exec_driver_sql("PRAGMA table_info(function_records)").fetchall()
        existing = {row[1] for row in rows}
        if "mesh_id" not in existing:
            conn.exec_driver_sql("ALTER TABLE function_records ADD COLUMN mesh_id TEXT")
        if "semantic_name" not in existing:
            conn.exec_driver_sql("ALTER TABLE function_records ADD COLUMN semantic_name TEXT")

        rows = conn.exec_driver_sql("PRAGMA table_info(function_records)").fetchall()
        existing = {row[1] for row in rows}
        columns = {
            "heartbeat_interval_s": "INTEGER",
            "last_heartbeat_at": "DATETIME",
            "expires_at": "DATETIME",
        }
        for name, col_type in columns.items():
            if name not in existing:
                conn.exec_driver_sql(f"ALTER TABLE function_records ADD COLUMN {name} {col_type}")

        idx_rows = conn.exec_driver_sql("PRAGMA index_list(function_records)").fetchall()
        has_unique_name = False
        for idx in idx_rows:
            idx_name = idx[1]
            unique = idx[2]
            if not unique:
                continue
            cols = conn.exec_driver_sql(f"PRAGMA index_info({idx_name})").fetchall()
            col_names = [c[2] for c in cols]
            if col_names == ["name"]:
                has_unique_name = True
                break

        if has_unique_name:
            conn.exec_driver_sql(
                """
                CREATE TABLE function_records_new (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    semantic_name TEXT,
                    mesh_id TEXT NOT NULL,
                    service_name TEXT NOT NULL,
                    runtime TEXT NOT NULL,
                    transport TEXT,
                    mcp_transport TEXT NOT NULL,
                    endpoint TEXT NOT NULL,
                    description TEXT,
                    input_schema TEXT,
                    output_schema TEXT,
                    acl TEXT,
                    cost TEXT,
                    tags TEXT,
                    version TEXT,
                    health TEXT,
                    heartbeat_interval_s INTEGER,
                    last_heartbeat_at DATETIME,
                    expires_at DATETIME,
                    created_at DATETIME,
                    updated_at DATETIME
                )
                """
            )

            conn.exec_driver_sql(
                """
                INSERT INTO function_records_new (
                    id, name, semantic_name, mesh_id, service_name, runtime, transport, mcp_transport, endpoint, description,
                    input_schema, output_schema, acl, cost, tags, version, health,
                    heartbeat_interval_s, last_heartbeat_at, expires_at, created_at, updated_at
                )
                SELECT
                    id,
                    name,
                    semantic_name,
                    COALESCE(mesh_id, service_name),
                    service_name,
                    runtime,
                    transport,
                    mcp_transport,
                    endpoint,
                    description,
                    input_schema,
                    output_schema,
                    acl,
                    cost,
                    tags,
                    version,
                    health,
                    heartbeat_interval_s,
                    last_heartbeat_at,
                    expires_at,
                    created_at,
                    updated_at
                FROM function_records
                """
            )

            conn.exec_driver_sql("DROP TABLE function_records")
            conn.exec_driver_sql("ALTER TABLE function_records_new RENAME TO function_records")
            conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_function_records_name ON function_records(name)")
            conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_function_records_semantic_name ON function_records(semantic_name)")
            conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_function_records_mesh_id ON function_records(mesh_id)")

    with Session(engine) as session:
        repo = FunctionRepository(session)
        records = session.exec(select(FunctionRecord)).all()
        for r in records:
            if not getattr(r, "semantic_name", None):
                r.semantic_name = repo.semanticize(r.name)
                session.add(r)
        session.commit()

def get_session():
    with Session(engine) as session:
        yield session
