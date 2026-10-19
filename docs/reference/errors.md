# Errors

The error classes: each has a stable `code`, `message`, `details` and `retryable` (see the [errors guide](../guides/errors.md)).

::: brevia
    options:
      show_root_heading: false
      members:
        - BreviaError
        - InvalidInput
        - OverrideNotAllowed
        - Unauthorized
        - Forbidden
        - NotFound
        - IdempotencyConflict
        - VersionConflict
        - NotReady
        - Busy
        - Unsupported
        - ProviderError
        - FileTooLarge
        - Unavailable
        - LimitExceeded
        - RunTimeout
        - OutputInvalid
        - ToolError
        - Cancelled
        - InternalError
