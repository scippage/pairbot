from contextvars import ContextVar

from .context import AppContext, InteractionContext

app: ContextVar[AppContext] = ContextVar("app")
interaction: ContextVar[InteractionContext] = ContextVar("interaction")
