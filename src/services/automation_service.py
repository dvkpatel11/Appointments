from __future__ import annotations

from src.domain.enums import ClientState
from src.domain.errors import InvalidStateError, NotFoundError
from src.infrastructure import logging as client_logging
from src.infrastructure.repositories import client_repo, state_repo
from src.orchestrator import manager as orchestrator
from src.services.client_service import ClientService


class AutomationService:
    @staticmethod
    def start(token: str) -> dict:
        client = ClientService.get_by_token(token)
        if not client:
            raise NotFoundError(f"Token {token[:12]}... not found")
        if not client.can_start:
            raise InvalidStateError(f"Client {client.id[:12]}... cannot start (state={client.state.value})")
        ok = orchestrator.start(client)
        if ok:
            client_repo.update_field(client.id, state="approved")
        return {"client_id": client.id, "started": ok}

    @staticmethod
    def stop(token: str) -> dict:
        client = ClientService.get_by_token(token)
        if not client:
            raise NotFoundError(f"Token {token[:12]}... not found")
        client_repo.update_field(client.id, state=ClientState.STOPPED.value)
        ok = orchestrator.stop(client.id)
        return {"client_id": client.id, "stopped": ok}

    @staticmethod
    def get_status(token: str) -> dict:
        client = ClientService.get_by_token(token)
        if not client:
            raise NotFoundError(f"Token {token[:12]}... not found")
        state = state_repo.load(client.id) or {}
        running = orchestrator.is_alive(client.id)
        return {
            "is_running": running,
            "client_state": client.state.value,
            **state,
        }

    @staticmethod
    def read_logs(client_id: str, lines: int = 200) -> str:
        return client_logging.read_client_log(client_id, lines)
