import json
import logging
import time
import uuid
from typing import Any, Optional

import redis as redis_lib
from google.adk.events import Event
from google.adk.sessions.base_session_service import (
    BaseSessionService,
    GetSessionConfig,
    ListSessionsResponse,
)
from google.adk.sessions.session import Session

logger = logging.getLogger(__name__)

TTL_PADRAO = 60 * 60 * 24 * 7  # 7 dias


class RedisSessionService(BaseSessionService):
    """Sessões persistentes no Redis — compatível com ambientes serverless."""

    def __init__(self, redis_url: str, ttl: int = TTL_PADRAO):
        self._r = redis_lib.from_url(redis_url, decode_responses=True, socket_timeout=5)
        self._ttl = ttl

    # ── chaves ──────────────────────────────────────────────────────────────

    def _key_events(self, app_name: str, user_id: str, session_id: str) -> str:
        return f"adk:events:{app_name}:{user_id}:{session_id}"

    def _key_state(self, app_name: str, user_id: str, session_id: str) -> str:
        return f"adk:state:{app_name}:{user_id}:{session_id}"

    def _key_index(self, app_name: str, user_id: str) -> str:
        return f"adk:sessions:{app_name}:{user_id}"

    # ── serialização ────────────────────────────────────────────────────────

    def _carregar_eventos(self, app_name: str, user_id: str, session_id: str) -> list[Event]:
        raw = self._r.lrange(self._key_events(app_name, user_id, session_id), 0, -1)
        eventos = []
        for item in raw:
            try:
                eventos.append(Event.model_validate_json(item))
            except Exception as exc:
                logger.warning(f"Evento inválido ignorado: {exc}")
        return eventos

    def _carregar_state(self, app_name: str, user_id: str, session_id: str) -> dict:
        raw = self._r.get(self._key_state(app_name, user_id, session_id))
        if raw:
            try:
                return json.loads(raw)
            except Exception:
                pass
        return {}

    # ── interface BaseSessionService ─────────────────────────────────────────

    async def create_session(
        self,
        *,
        app_name: str,
        user_id: str,
        state: Optional[dict[str, Any]] = None,
        session_id: Optional[str] = None,
    ) -> Session:
        sid = session_id or str(uuid.uuid4())
        eventos = self._carregar_eventos(app_name, user_id, sid)
        estado = self._carregar_state(app_name, user_id, sid)
        if state:
            estado.update(state)

        # Regista a sessão no índice do utilizador
        self._r.sadd(self._key_index(app_name, user_id), sid)
        self._r.expire(self._key_index(app_name, user_id), self._ttl)

        return Session(
            id=sid,
            app_name=app_name,
            user_id=user_id,
            state=estado,
            events=eventos,
            last_update_time=time.time(),
        )

    async def get_session(
        self,
        *,
        app_name: str,
        user_id: str,
        session_id: str,
        config: Optional[GetSessionConfig] = None,
    ) -> Optional[Session]:
        if not self._r.exists(self._key_events(app_name, user_id, session_id)) and \
           not self._r.sismember(self._key_index(app_name, user_id), session_id):
            return None
        eventos = self._carregar_eventos(app_name, user_id, session_id)
        estado = self._carregar_state(app_name, user_id, session_id)
        return Session(
            id=session_id,
            app_name=app_name,
            user_id=user_id,
            state=estado,
            events=eventos,
            last_update_time=time.time(),
        )

    async def list_sessions(self, *, app_name: str, user_id: str) -> ListSessionsResponse:
        sids = self._r.smembers(self._key_index(app_name, user_id))
        sessions = []
        for sid in sids:
            s = await self.get_session(app_name=app_name, user_id=user_id, session_id=sid)
            if s:
                sessions.append(s)
        return ListSessionsResponse(sessions=sessions)

    async def delete_session(self, *, app_name: str, user_id: str, session_id: str) -> None:
        self._r.delete(
            self._key_events(app_name, user_id, session_id),
            self._key_state(app_name, user_id, session_id),
        )
        self._r.srem(self._key_index(app_name, user_id), session_id)

    async def append_event(self, session: Session, event: Event) -> Event:
        # Chama a lógica base (atualiza state_delta, etc.)
        event = await super().append_event(session, event)
        if event.partial:
            return event

        key_ev = self._key_events(session.app_name, session.user_id, session.id)
        key_st = self._key_state(session.app_name, session.user_id, session.id)

        # Persiste o evento
        self._r.rpush(key_ev, event.model_dump_json())
        self._r.expire(key_ev, self._ttl)

        # Persiste o state
        if session.state:
            self._r.setex(key_st, self._ttl, json.dumps(session.state))

        return event
