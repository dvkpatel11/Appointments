from enum import StrEnum


class ClientState(StrEnum):
    ISSUED = "issued"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    STOPPED = "stopped"


class VisaType(StrEnum):
    CANADA = "canada"
    UK = "uk"
