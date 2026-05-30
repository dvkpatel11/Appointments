class DomainError(Exception):
    """Base domain error."""


class NotFoundError(DomainError):
    """Entity not found."""


class InvalidStateError(DomainError):
    """Operation not allowed in current state."""


class AutomationError(DomainError):
    """Automation operation failed."""
