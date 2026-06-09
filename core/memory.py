import os
import logging
from sqlalchemy import create_engine, text

logger = logging.getLogger(__name__)

_engine = None


def _get_engine():
    global _engine
    if _engine is None:
        db_url = os.environ.get("DATABASE_URL", "")
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://", 1)
        _engine = create_engine(db_url, pool_pre_ping=True)
        _init_table()
    return _engine


def _init_table():
    with _engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS bot_perfis_cliente (
                sender_id       TEXT PRIMARY KEY,
                perfil          TEXT NOT NULL,
                criado_em       TIMESTAMPTZ DEFAULT NOW(),
                atualizado_em   TIMESTAMPTZ DEFAULT NOW()
            )
        """))
        conn.commit()


def get_perfil(sender_id: str) -> str | None:
    try:
        with _get_engine().connect() as conn:
            row = conn.execute(
                text("SELECT perfil FROM bot_perfis_cliente WHERE sender_id = :sid"),
                {"sid": sender_id},
            ).fetchone()
            return row[0] if row else None
    except Exception as e:
        logger.error(f"get_perfil error: {e}")
        return None


def save_perfil(sender_id: str, perfil: str) -> None:
    try:
        with _get_engine().connect() as conn:
            conn.execute(text("""
                INSERT INTO bot_perfis_cliente (sender_id, perfil, atualizado_em)
                VALUES (:sid, :perfil, NOW())
                ON CONFLICT (sender_id) DO UPDATE
                SET perfil = :perfil, atualizado_em = NOW()
            """), {"sid": sender_id, "perfil": perfil})
            conn.commit()
    except Exception as e:
        logger.error(f"save_perfil error: {e}")
