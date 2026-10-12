"""Stable error codes shared by use cases and the HTTP adapter."""

STATUS_BY_CODE = {
    "MALFORMED_JSON": 400,
    "IDEMPOTENCY_KEY_REQUIRED": 400,
    "INVALID_IDEMPOTENCY_KEY": 400,
    "INVALID_STATE_VERSION_HEADER": 400,
    "VISITOR_AUTH_REQUIRED": 401,
    "ORIGIN_NOT_ALLOWED": 403,
    "CASE_NOT_FOUND": 404,
    "SESSION_NOT_FOUND": 404,
    "SCENE_NOT_FOUND": 404,
    "NPC_NOT_FOUND": 404,
    "REQUEST_NOT_FOUND": 404,
    "ROUTE_NOT_FOUND": 404,
    "METHOD_NOT_ALLOWED": 405,
    "IDEMPOTENCY_KEY_CONFLICT": 409,
    "STATE_VERSION_CONFLICT": 409,
    "SESSION_NOT_CURRENT": 409,
    "CURRENT_SESSION_EXISTS": 409,
    "CURRENT_SESSION_CONFLICT": 409,
    "CASE_UNAVAILABLE": 409,
    "ACTION_NOT_ALLOWED": 409,
    "ACTION_UNAVAILABLE": 409,
    "NPC_UNAVAILABLE": 409,
    "ACTIVE_NPC_MISMATCH": 409,
    "ACCUSATION_ALREADY_SUBMITTED": 409,
    "REVIEW_NOT_AVAILABLE": 409,
    "SAVE_VERSION_UNSUPPORTED": 409,
    "PAYLOAD_TOO_LARGE": 413,
    "UNSUPPORTED_MEDIA_TYPE": 415,
    "VALIDATION_ERROR": 422,
    "INVALID_ACTION_REFERENCE": 422,
    "EVIDENCE_NOT_OWNED": 422,
    "INVALID_ACCUSATION_OPTION": 422,
    "CONFIRMATION_REQUIRED": 422,
    "STATE_VERSION_REQUIRED": 428,
    "CASE_CONFIGURATION_ERROR": 500,
    "SAVE_INTEGRITY_ERROR": 500,
    "INTERNAL_ERROR": 500,
    "PERSISTENCE_UNAVAILABLE": 503,
}


class ApiProblem(Exception):
    """A rejected request with a safe message; details never carry hidden case data."""

    def __init__(
        self, code: str, message: str, details: dict | None = None, retryable: bool = False
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}
        self.retryable = retryable

    @property
    def status(self) -> int:
        return STATUS_BY_CODE[self.code]

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "message": self.message,
            "details": self.details,
            "retryable": self.retryable,
        }
