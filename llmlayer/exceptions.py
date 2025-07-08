class LLMLayerError(RuntimeError):
    """Base class for all SDK errors."""


class InvalidRequest(LLMLayerError):
    pass


class AuthenticationError(LLMLayerError):
    pass


class ProviderError(LLMLayerError):
    pass


class RateLimitError(LLMLayerError):
    pass


class InternalServerError(LLMLayerError):
    pass
