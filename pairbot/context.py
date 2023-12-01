
import contextvars
from types import TracebackType
from typing import (
    Any,
    Self,
)

from discord import Interaction

from . import globals
from .app import App

class AppContext:
    """The app context contains application-specific information (similar to Flask's application
    context)."""

    def __init__(
        self,
        app: App,
    ):
        self.app = app
        self._cv_tokens: list[contextvars.Token] = []

    def push(self) -> None:
        """Binds the app context to the current context."""
        self._cv_tokens.append(globals.app.set(self))

    def pop(self, exc: BaseException | None):
        ctx = globals.app.get()
        assert ctx is self
        globals.app.reset(self._cv_tokens.pop())

    def __enter__(self) -> Self:
        self.push()
        return self

    def __exit__(
        self,
        exc_type: type | None,
        exc_value: BaseException | None,
        tb: TracebackType | None
    ) -> None:
        self.pop(exc_value)


class InteractionContext:
    """The interaction context contains interaction-specific information (similar to Flask's request
    context). It is created and pushed at the beginning of an interaction, and popped at the end."""

    def __init__(
        self,
        app: App,
        interaction: Interaction[Any],
    ):
        self.app = app
        self.interaction = interaction
