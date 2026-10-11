from alembic import context
from sqlalchemy import create_engine, pool

from backend.config import Settings
from backend.infrastructure.database.models import Base

database_url = str(Settings().database_url)

if context.is_offline_mode():
    context.configure(
        url=database_url,
        target_metadata=Base.metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = create_engine(database_url, poolclass=pool.NullPool)
    try:
        with engine.connect() as connection:
            context.configure(connection=connection, target_metadata=Base.metadata)
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()
