"""Insert fictional demo data. Run from the repository root: python -m db.seed."""
from backend.main import engine, meta, ROOT

meta.create_all(engine)
sql = (ROOT / 'db' / 'seed.sql').read_text(encoding='utf-8')
with engine.begin() as conn:
    for statement in sql.split(';'):
        if statement.strip():
            conn.exec_driver_sql(statement)
print('Demo ready: demo@example.test / DemoFamily123!')
