from enum import StrEnum


class ExportColumns(StrEnum):
    """String enum for column names used in Splitwise exports."""

    DATE = "date"
    AMOUNT = "amount"
    DESCRIPTION = "description"
    FINGERPRINT = "fingerprint"
    ID = "id"
