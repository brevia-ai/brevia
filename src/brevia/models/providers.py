"""Provider clients shared by the model calls of a process.

Pydantic AI creates a new provider, SDK client and connection pool for every model it
resolves from a reference; the SDK clients also retry failed requests on their own,
outside the run limits. The providers here are created once per provider name, with
the credentials of the environment as Pydantic AI reads them, and with the retries of
the SDK turned off: Brevia retries temporary errors itself, counting each attempt
(see :func:`brevia.models.client.generate_once`). :func:`close_providers` closes their
connections; the next call creates them again.

Connections belong to an event loop, so providers are kept per running loop. Each
started :class:`~brevia.Brevia` holds them (:func:`hold_providers`); they are closed
when the last one stops, so that stopping one instance does not break the calls of
another.
"""

from __future__ import annotations

import asyncio
import logging
import weakref
from typing import Any

from pydantic_ai.providers import Provider
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.providers.ollama import OllamaProvider
from pydantic_ai.providers.openai import OpenAIProvider

logger = logging.getLogger(__name__)

ANTHROPIC_LOGGER = "anthropic._base_client"
"""Logger of the Anthropic SDK that writes the options of each request, body
included, at the ``DEBUG`` level."""


class _NoRequestOptions(logging.Filter):
    """Drop the records of the request options: they hold the prompts and the
    documents sent to the model."""

    def filter(self, record: logging.LogRecord) -> bool:
        return not str(record.msg).startswith("Request options")


def guard_sdk_logs() -> None:
    """Install the filter of the request options logged by the Anthropic SDK.
    Repeatable; called before every model request, not at import."""
    sdk = logging.getLogger(ANTHROPIC_LOGGER)
    if not any(isinstance(item, _NoRequestOptions) for item in sdk.filters):
        sdk.addFilter(_NoRequestOptions())


_CLASSES: dict[str, tuple[type[Provider[Any]], str]] = {
    "openai": (OpenAIProvider, "openai_client"),
    "anthropic": (AnthropicProvider, "anthropic_client"),
    "ollama": (OllamaProvider, "openai_client"),
}
"""Provider classes by name, with the argument that receives an SDK client."""

# Keyed by the loop itself, not by its id: the id of a closed loop can be reused.
_providers: weakref.WeakKeyDictionary[object, dict[str, Provider[Any]]] = (
    weakref.WeakKeyDictionary()
)
_holders: weakref.WeakKeyDictionary[object, int] = weakref.WeakKeyDictionary()


class _Outside:
    """Key of the providers resolved outside a loop, without connecting."""


_OUTSIDE = _Outside()


def _loop() -> object:
    try:
        return asyncio.get_running_loop()
    except RuntimeError:
        return _OUTSIDE


def provider(name: str) -> Provider[Any]:
    """The shared provider ``name``, created at its first use.

    Raises:
        pydantic_ai.exceptions.UserError: The provider is unknown, or its
            credentials or base URL are missing from the environment.
    """
    shared_here = _providers.setdefault(_loop(), {})
    shared = shared_here.get(name)
    if shared is not None:
        return shared
    try:
        provider_class, argument = _CLASSES[name]
    except KeyError:
        from pydantic_ai.exceptions import UserError

        raise UserError(f"Unknown model provider {name!r}") from None
    # Built as Pydantic AI builds it, which checks the environment, then again on a
    # copy of its client without retries; the copy shares the connection pool.
    configured = provider_class()
    client = configured.client.with_options(max_retries=0)
    shared = provider_class(**{argument: client})
    shared_here[name] = shared
    return shared


def hold_providers() -> None:
    """Record a user of the providers of the running loop, until it releases them."""
    loop = _loop()
    _holders[loop] = _holders.get(loop, 0) + 1


async def release_providers() -> None:
    """Release a hold; the last one closes the providers of the running loop."""
    loop = _loop()
    left = _holders.get(loop, 0) - 1
    if left > 0:
        _holders[loop] = left
        return
    _holders.pop(loop, None)
    await close_providers()


async def close_providers() -> None:
    """Close the connections of the shared providers of the running loop."""
    closing = [shared.client.close() for shared in _providers.pop(_loop(), {}).values()]
    results = await asyncio.gather(*closing, return_exceptions=True)
    for result in results:
        if isinstance(result, BaseException):
            logger.warning(
                "A model provider client did not close: %s", type(result).__name__
            )
