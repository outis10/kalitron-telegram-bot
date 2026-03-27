class ValidationIntegrationError(Exception):
    pass


class ValidationCompatibilityError(ValidationIntegrationError):
    pass


class ClientResolutionError(ValidationIntegrationError):
    pass


class ClientOnboardingError(ValidationIntegrationError):
    pass


class ValidationRequestError(ValidationIntegrationError):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class ValidationTransportError(ValidationIntegrationError):
    pass
