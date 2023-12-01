"""discord.py

Utilities for interfacing with the Discord API."""

from abc import ABC
from typing import (
    Any,
    Callable,
    Concatenate,
    Coroutine,
    ParamSpec,
    TypeVar,
    TypedDict,
    Union,
)

import functools
import logging

import discord

logger = logging.getLogger(__name__)


class AppContext(TypedDict):
    logger_adapter: Union[logging.Logger, logging.LoggerAdapter]


class AppCommandLoggerAdapter(logging.LoggerAdapter):
    """Custom LoggerAdapter for adding context to logs."""
    def process(self, msg: str, kwargs: dict):
        """Add guild, channel, and user IDs to slash command logs."""
        if self.extra is None:
            return msg, kwargs

        guild_id = self.extra.get("guild_id")
        channel_id = self.extra.get("channel_id")
        user_id = self.extra.get("user_id")

        s = ""
        if guild_id is not None: s += f"g: <{guild_id} "
        if channel_id is not None: s += f"c: <{channel_id} "
        if user_id is not None: s += f"u: <{user_id} "
        s += msg

        return s, kwargs

# Type fuckery for the command decorator
T = TypeVar("T")
P = ParamSpec("P")
CommandCallback = Callable[Concatenate[AppContext, discord.Interaction[Any], P], Coroutine[Any, Any, T]]


class Application(ABC):
    """A wrapper around a discord client instance."""

    def __init__(
        self,
        intents: discord.Intents = discord.Intents.all(),
        **options: Any
    ):
        self.client = discord.Client(intents=intents, **options)
        self.command_tree = discord.app_commands.CommandTree(self.client)

    def get_context(self, interaction: discord.Interaction[Any]) -> AppContext:
        return {
            "logger_adapter": AppCommandLoggerAdapter(
                logger,
                {
                    "guild_id": interaction.guild_id,
                    "channel_id": interaction.channel_id,
                    "user_id": interaction.user.id,
                }
            ),
        }

    def command(self, **options: Any):
        """Wrapper for adding logging and error-handling to application slash commands."""
        def decorator(callback: CommandCallback):
            @self.command_tree.command(**options)
            @functools.wraps(callback)
            async def wrapper(interaction: discord.Interaction[Any], *args: P.args, **kwargs: P.kwargs) -> None:
                await callback(
                    self.get_context(interaction),
                    interaction,
                    *args,
                    **kwargs
                )
            return wrapper
        return decorator
