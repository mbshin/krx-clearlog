class KrxParserError(Exception):
    pass


class SchemaValidationError(KrxParserError):
    pass


class UnknownMessageType(KrxParserError):
    def __init__(self, transaction_code: str) -> None:
        super().__init__(f"unknown TRANSACTION_CODE: {transaction_code!r}")
        self.transaction_code = transaction_code


class FieldDecodeError(KrxParserError):
    def __init__(self, field_name: str, raw: bytes, reason: str) -> None:
        super().__init__(f"failed to decode field {field_name!r}: {reason} (raw={raw!r})")
        self.field_name = field_name
        self.raw = raw
        self.reason = reason
