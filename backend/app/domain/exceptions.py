class DomainError(Exception):
    """Base error for expected business-rule failures."""


class ResourceNotFound(DomainError):
    pass


class ValidationBlocked(DomainError):
    pass


class ApprovalRequired(DomainError):
    pass

