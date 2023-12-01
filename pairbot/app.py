import pdb
import sys

from typing import (
    Any,
    Callable,
    Concatenate,
    Coroutine,
    ParamSpec,
    TypeVar,
)

import logging
from functools import wraps
from contextvars import ContextVar

import discord

logger = logging.getLogger(__name__)

# Globally accessible context variables
interaction_ctx: ContextVar[discord.Interaction[Any]] = ContextVar("interaction")


class InteractionContext:
    def __init__(self, interaction: discord.Interaction[Any]):
        self.interaction = interaction
        self.token = None

    def __enter__(self) -> None:
        self.token = interaction_ctx.set(self.interaction)

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self.token is not None:
            interaction_ctx.reset(self.token)


class InteractionLoggingAdapter(logging.LoggerAdapter):
    """A custom formatter for logging inside an interaction context"""
    def process(self, msg, kwargs):
        interaction = interaction_ctx.get(None)
        new_msg = ""
        if interaction is not None:
            new_msg += "Interaction"
            if interaction.guild is not None:
                new_msg += f" in guild \"{interaction.guild.name}\" ({interaction.guild.id})"
            if interaction.channel is not None and isinstance(interaction.channel, discord.TextChannel):
                new_msg += f" channel \"#{interaction.channel.name} ({interaction.channel.id})\""
            new_msg += f" by user \"@{interaction.user.name}\" ({interaction.user.id}): "
        new_msg += str(msg)
        return new_msg, kwargs


# Type fuckery for the command decorator
T = TypeVar("T")
P = ParamSpec("P")
CommandCallback = Callable[Concatenate[discord.Interaction[Any], P], Coroutine[Any, Any, T]]

class DiscordApp:
    """A wrapper around a discord client instance."""
    def __init__(self, intents: discord.Intents, **options: Any):
        self.client = discord.Client(intents=intents, **options)
        self.command_tree = discord.app_commands.CommandTree(self.client)
        self.logger = InteractionLoggingAdapter(logger)

        # register on_ready event
        @self.client.event
        async def on_ready():
            for guild in self.client.guilds:
                self.logger.info("Copying command tree to guild \"%s\" (%d)", guild.name, guild.id)
                self.command_tree.copy_global_to(guild=guild)
                await self.command_tree.sync(guild=guild)
            self.logger.info("Application ready.")

    def command(self, **options: Any):
        """Wrapper around discord slash commands."""
        def decorator(callback: CommandCallback):
            @self.command_tree.command(**options)
            @wraps(callback)
            async def wrapper(i: discord.Interaction[Any], *args: P.args, **kwargs: P.kwargs) -> None:
                assert i.command is not None
                pretty_kwargs = (
                    " with arguments { " +
                    ", ".join((f"{key}=\"{str(value)}\"" for key, value in kwargs.items())) +
                    " }"
                    if len(kwargs) > 0 else " with no arguments"
                )
                self.logger.info("Executing slash command /%s%s", i.command.name, pretty_kwargs)
                try:
                    with InteractionContext(i):
                        await callback(i, *args, **kwargs)
                except Exception as e:
                    self.logger.error(e, exc_info=True)
                    await i.response.send_message("Pairbot broke somehow :v", ephemeral=True)
            return wrapper
        return decorator

    def run(self, token: str, *args, **kwargs):
        self.client.run(token, *args, **kwargs)
