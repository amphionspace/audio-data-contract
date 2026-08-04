class ContractError(ValueError):
    """Raised when serialized data violates a public contract."""


class ResolutionError(ContractError):
    """Raised when a portable artifact cannot be resolved on this machine."""


class StateTransitionError(ContractError):
    """Raised when a dataset state transition is not allowed."""
