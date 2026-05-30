from enum import Enum


class ClientState(str, Enum):
    ISSUED = "issued"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    STOPPED = "stopped"


class VisaType(str, Enum):
    CANADA = "canada"
    UK = "uk"
