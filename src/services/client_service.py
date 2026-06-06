from __future__ import annotations

from datetime import datetime

from src.domain.client import Client
from src.domain.enums import ClientState
from src.domain.errors import InvalidStateError, NotFoundError
from src.infrastructure.repositories import client_repo


class ClientService:
    @staticmethod
    def generate_link() -> str:
        return client_repo.create_token()

    @staticmethod
    def get_by_token(token: str) -> Client | None:
        return client_repo.get_by_token(token)

    @staticmethod
    def get_by_id(client_id: str) -> Client | None:
        return client_repo.get_by_id(client_id)

    @staticmethod
    def get_pending() -> dict[str, Client]:
        return client_repo.get_by_state(ClientState.PENDING)

    @staticmethod
    def get_approved() -> dict[str, Client]:
        return client_repo.get_by_state(ClientState.APPROVED)

    @staticmethod
    def get_all() -> dict[str, Client]:
        return client_repo.get_all()

    @staticmethod
    def submit_request(token: str, form_data: dict) -> Client:
        client = client_repo.get_by_token(token)
        if not client:
            raise NotFoundError(f"Token {token[:12]}... not found")
        if client.state in (ClientState.APPROVED, ClientState.PENDING):
            raise InvalidStateError(f"Client is already {client.state.value}")

        client.state = ClientState.PENDING
        client.name = form_data.get("name", "Client")
        client.username = form_data.get("username", "").strip()
        client.password = form_data.get("password", "")
        client.appointment_id = form_data.get("appointment_id", "").strip()
        client.appointment_url = form_data.get("appointment_url", "")
        client.reschedule = form_data.get("reschedule") == "true"
        client.preferred_locations = form_data.get("preferred_locations")
        client.preferred_date_from = form_data.get("preferred_date_from", "").strip() or None
        client.preferred_date_to = form_data.get("preferred_date_to", "").strip() or None
        # NOTE: notification_email is intentionally NOT set here. It is only
        # written to the client row after the user clicks the magic link
        # sent by /send_email_magic_link. Use the wizard's Step 3 to enter
        # an email, or use the monitor panel's Email tile post-approval.
        client.telegram_chat_id = form_data.get("telegram_chat_id", "").strip() or None
        client.updated_at = datetime.utcnow()

        client_repo.save(client)
        return client

    @staticmethod
    def approve(token: str) -> Client:
        client = client_repo.get_by_token(token)
        if not client:
            raise NotFoundError(f"Token {token[:12]}... not found")
        if client.state != ClientState.PENDING:
            raise InvalidStateError(f"Can only approve pending requests, got {client.state.value}")

        client.state = ClientState.APPROVED
        client.updated_at = datetime.utcnow()
        client_repo.save(client)
        return client

    @staticmethod
    def reject(token: str, reason: str = "Your request was not approved at this time.") -> Client:
        client = client_repo.get_by_token(token)
        if not client:
            raise NotFoundError(f"Token {token[:12]}... not found")
        client.state = ClientState.REJECTED
        client.reject_reason = reason
        client.updated_at = datetime.utcnow()
        client_repo.save(client)
        return client

    @staticmethod
    def update_notification(client_id: str, email: str | None = None, phone: str | None = None) -> Client:
        client = client_repo.get_by_id(client_id)
        if not client:
            raise NotFoundError(f"Client {client_id[:12]}... not found")
        if email is not None:
            client.notification_email = email
        if phone is not None:
            client.phone_number = phone
        client.updated_at = datetime.utcnow()
        client_repo.save(client)
        return client
