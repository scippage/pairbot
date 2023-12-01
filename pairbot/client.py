"""client.py

This module describes the Discord slash command interface and corresponding logic.
"""

import functools
import logging

from typing import (
    Any,
    Optional,
    TypeVar,
    ParamSpec,
    Callable,
    Concatenate,
    Coroutine,
)

import sqlalchemy
from sqlalchemy import (
    create_engine,
    func,
    or_,
)
import sqlalchemy.orm
from sqlalchemy.orm import (
    Session,
    sessionmaker,

)

import discord
import discord.ext.commands
import discord.ext.tasks

from datetime import datetime, timedelta
import dateparser

from . import (
    config,
)

from .models import (
    Weekday,
    PairingChannel,
    Schedule,
    ScheduleAdjustment,
    Pairing,
)

logger = logging.getLogger(__name__)

# type fuckery for the command decorator
T = TypeVar("T")
P = ParamSpec("P")
CommandCallback = Callable[Concatenate[discord.Interaction[Any], P], Coroutine[Any, Any, T]]

class Pairbot(discord.Client):
    """Represents a running instance of Pairbot."""

    def __init__(self, intents: discord.Intents, **options: Any) -> None:
        super().__init__(intents=intents, **options)
        self.tree = discord.app_commands.CommandTree(self)

        self.db_engine = create_engine(config.DATABASE_URL)
        self.make_orm_session = sessionmaker(self.db_engine)

    def command(
        self,
        **options: Any
    ):
        """Wrapper for pairbot slash commands with logging and error-handling."""
        def decorator(callback: CommandCallback):
            @self.tree.command(**options)
            @discord.app_commands.guild_only()
            @functools.wraps(callback)
            async def wrapper(
                interaction: discord.Interaction[Any],
                *args: P.args,
                **kwargs: P.kwargs,
            ) -> None:
                # Keep type checker happy
                assert interaction.command is not None
                assert interaction.guild is not None
                assert isinstance(interaction.channel, discord.TextChannel)
                assert isinstance(interaction.user, discord.Member)

                # Log command execution
                pretty_kwargs = (
                    " with arguments { " +
                    ", ".join((f"{key}=\"{str(value)}\"" for key, value in kwargs.items())) +
                    " }"
                    if len(kwargs) > 0 else " with no arguments"
                )
                logger.info(
                    f"User \"{interaction.user.name}\" executed command /{interaction.command.name}{pretty_kwargs} in guild \"{interaction.guild.name}\", channel \"#{interaction.channel.name}\"."
                )

                try:
                    await callback(interaction, *args, **kwargs)
                except Exception as e:
                    logger.error(e, exc_info=True)
                    await interaction.response.send_message("Pairbot broke somehow! :v", ephemeral=True)

            return wrapper
        return decorator

    async def on_ready(self) -> None:
        for guild in self.guilds:
            logger.info(f"Copying command tree to guild \"{guild.name}\"")
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        logger.info("Pairbot ready.")


# Instantiate client and register slash commands
intents = discord.Intents.all()
client = Pairbot(
    intents=intents,
)


@client.command(
    name="addpairbot",
    description="Add Pairbot to the current channel."
)
@discord.app_commands.checks.has_permissions(administrator=True)
async def _add_pairbot(interaction: discord.Interaction):
    assert interaction.guild is not None
    assert isinstance(interaction.channel, discord.TextChannel)

    session = client.make_orm_session()
    with session.begin():
        channel = (
            session.query(PairingChannel)
            .filter(PairingChannel.channel_id == interaction.channel_id)
            .one_or_none()
        )

        if channel is not None:
            if channel.active:
                logger.info(
                    f"Pairbot is already added to guild \"{interaction.guild.name}\", channel \"#{interaction.channel}\"."
                )
                await interaction.response.send_message(
                    f"Pairbot is already added to \"#{interaction.channel.name}\"."
                )
                return
            else:
                channel.active = True
        else:
            channel = PairingChannel(
                guild_id = interaction.guild.id,
                channel_id = interaction.channel.id,
                active = True,
                leetcode_integration = False, # TODO
            )
            session.add(channel)

        session.commit()

        logger.info(
            f"Added Pairbot to guild \"{interaction.guild.name}\", channel \"#{interaction.channel.name}\"."
        )
        await interaction.response.send_message(
            f"Added Pairbot to \"#{interaction.channel.name}\"."
        )


@client.command(
    name="removepairbot",
    description="Remove Pairbot from the current channel."
)
@discord.app_commands.guild_only()
@discord.app_commands.checks.has_permissions(administrator=True)
async def _remove_pairbot(interaction: discord.Interaction):
    assert interaction.guild is not None
    assert isinstance(interaction.channel, discord.TextChannel)

    session = client.make_orm_session()
    with session.begin():
        channel = (
            session.query(PairingChannel)
            .filter(PairingChannel.channel_id == interaction.channel_id)
            .one_or_none()
        )

        if channel is None or not channel.active:
            logger.info(
                f"Pairbot is not added to guild \"{interaction.guild.name}\", channel \"#{interaction.channel}\"."
            )
            await interaction.response.send_message(
                f"Pairbot is not added to \"#{interaction.channel.name}\"."
            )
        else:
            channel.active = False
            session.commit()
            logger.info(
                f"Removed Pairbot from guild \"{interaction.guild.name}\", channel \"#{interaction.channel.name}\"."
            )
            await interaction.response.send_message(
                f"Removed Pairbot from \"#{interaction.channel.name}\"."
            )


@client.command(
    name="subscribe",
    description="Subscribe to pair programming (every day if no weekday specified)."
)
@discord.app_commands.guild_only()
async def _subscribe(
    interaction: discord.Interaction,
    weekday: Optional[Weekday],
):
    assert interaction.guild is not None
    assert isinstance(interaction.channel, discord.TextChannel)
    session = client.make_orm_session()
    with session.begin():
        channel = (
            session.query(PairingChannel)
            .filter(PairingChannel.channel_id == interaction.channel_id)
            .one_or_none()
        )
        if channel is None:
            await interaction.response.send_message(
                f"Pairbot is not active in this channel.",
                ephemeral=True
            )
            return

        schedule = (
            session.query(Schedule)
            .filter(Schedule.channel_id == interaction.channel_id)
            .filter(Schedule.user_id == interaction.user.id)
            .one_or_none()
        )

        if schedule is None:
            schedule = Schedule(
                channel_id = interaction.channel_id,
                user_id = interaction.user.id,
            )
            session.add(schedule)

        if weekday is not None:
            if schedule[weekday] == True:
                await interaction.response.send_message(
                    f"You are already subscribed to pair programming on {str(weekday)} in #{interaction.channel.name}.",
                    ephemeral=True
                )
                return
            else:
                schedule[weekday] = True

            session.commit()

            logger.info(
                f"Subscribed user \"{interaction.user.name}\" to pair programming on {str(weekday)} in guild \"{interaction.guild.name}\", channel \"#{interaction.channel.name}\"."
            )

            msg = f"Successfully subscribed to pair programming on {str(weekday)} in #{interaction.channel.name}."
        else:
            if len(schedule.days_available) == 7:
                await interaction.response.send_message(
                    f"You are already subscribed to pair programming every day.",
                    ephemeral=True
                )
                return
            for day in Weekday:
                schedule[day] = True

            session.commit()

            logger.info(
                f"Subscribed user \"{interaction.user.name}\" to daily pair programming in guild \"{interaction.guild.name}\", channel \"#{interaction.channel.name}\"."
            )

            msg = f"Successfully subscribed to daily pair programming in #{interaction.channel.name}."
    await interaction.response.send_message(msg, ephemeral=True)


@client.command(
    name="unsubscribe",
    description="Unsubscribe from pair programming (every day if no weekday specified)."
)
@discord.app_commands.guild_only()
async def _unsubscribe(
    interaction: discord.Interaction,
    weekday: Optional[Weekday],
):
    assert interaction.guild is not None
    assert isinstance(interaction.channel, discord.TextChannel)

    session = client.make_orm_session()
    with session.begin():
        channel = (
            session.query(PairingChannel)
            .filter(PairingChannel.channel_id == interaction.channel_id)
            .one_or_none()
        )
        if channel is None:
            await interaction.response.send_message(
                f"Pairbot is not active in this channel.",
                ephemeral=True
            )
            return

        schedule = (
            session.query(Schedule)
            .filter(Schedule.channel_id == interaction.channel_id)
            .filter(Schedule.user_id == interaction.user.id)
            .one_or_none()
        )

        if schedule is None:
            await interaction.response.send_message(
                f"You are already not subscribed to pair programming in #{interaction.channel.name}.",
                ephemeral=True
            )
            return

        if weekday is not None:
            if not schedule[weekday]:
                await interaction.response.send_message(
                    f"You are already not subscribed to pair programming on {str(weekday)} in #{interaction.channel.name}.",
                    ephemeral=True
                )
                return

            schedule[weekday] = False
            session.commit()

            logger.info(
                f"Unsubscribed user \"{interaction.user.name}\" from pair programming on {str(weekday)} in guild \"{interaction.guild.name}\", channel \"#{interaction.channel.name}\"."
            )

            msg = f"Successfully unsubscribed from pair programming on {str(weekday)} in #{interaction.channel.name}."
        else:
            if len(schedule.days_available) == 0:
                await interaction.response.send_message(
                    f"You are already not subscribed to pair programming.",
                    ephemeral=True
                )
                return
            for day in Weekday:
                schedule[day] = False
            session.commit()

            logger.info(
                f"Unsubscribed user \"{interaction.user.name}\" from all pair programming in guild \"{interaction.guild.name}\", channel \"#{interaction.channel.name}\"."
            )

            msg = f"Successfully unsubscribed from all pair programming in #{interaction.channel.name}."

    await interaction.response.send_message(msg, ephemeral=True)


@client.command(
    name="skip",
    description="Mark yourself as unavailable for pair programming on some date in the future)."
)
@discord.app_commands.describe(human_date="A human-readable date like \"tomorrow\" or \"January 1\".")
@discord.app_commands.guild_only()
async def _skip(
    interaction: discord.Interaction,
    human_date: Optional[str],
):
    assert interaction.guild is not None
    assert isinstance(interaction.channel, discord.TextChannel)

    session = client.make_orm_session()
    with session.begin():
        channel = (
            session.query(PairingChannel)
            .filter(PairingChannel.channel_id == interaction.channel_id)
            .one_or_none()
        )
        if channel is None:
            await interaction.response.send_message(
                f"Pairbot is not active in this channel.",
                ephemeral=True
            )
            return

        schedule = (
            session.query(Schedule)
            .filter(Schedule.channel_id == interaction.channel_id)
            .filter(Schedule.user_id == interaction.user.id)
            .one_or_none()
        )

        if schedule is None or len(schedule.days_available) == 0:
            await interaction.response.send_message(
                f"You are not subscribed to pair programming in #{interaction.channel.name}.",
                ephemeral=True
            )
            return

        if human_date is None:
            adjustment_date = None
            current_weekday = datetime.now().weekday()
            for i in range(0, 7):
                weekday = Weekday((current_weekday + i) % 7)
                if schedule[weekday]:
                    adjustment_date = datetime.now().date() + timedelta(days=i)
                    break

            assert adjustment_date is not None
        else:
            # Clean things up for the parser
            cleaned_date = human_date.lower()
            cleaned_date = cleaned_date.replace("next", "")

            # Try to parse the date
            adjustment_datetime = dateparser.parse(
                cleaned_date,
                settings={
                    "PREFER_DATES_FROM": "future",
                    "RELATIVE_BASE": datetime.now(),
                },
                languages=["en"],
            )
            if adjustment_datetime is None:
                await interaction.response.send_message(
                    f"Could not parse date \"{human_date}\".",
                    ephemeral=True
                )
                return

            adjustment_date = adjustment_datetime.date()
            if adjustment_datetime < datetime.now():
                await interaction.response.send_message(
                    f"Cannot skip a date in the past: {adjustment_date.strftime('%A %B %d, %Y')}.",
                    ephemeral=True
                )
                return

            weekday = Weekday(adjustment_date.weekday())
            if schedule[weekday] == False:
                await interaction.response.send_message(
                    f"You are not subscribed to pair programming in #{interaction.channel.name} on {weekday}.",
                    ephemeral=True
                )
                return

        adjustment = (
            session.query(ScheduleAdjustment)
            .filter(ScheduleAdjustment.channel_id == interaction.channel_id)
            .filter(ScheduleAdjustment.user_id == interaction.user.id)
            .filter(func.DATE(ScheduleAdjustment.date) == adjustment_date)
            .one_or_none()
        )

        if adjustment is None:
            adjustment = ScheduleAdjustment(
                channel_id=interaction.channel_id,
                user_id=interaction.user.id,
                date=adjustment_date,
                available=False,
            )
            session.add(adjustment)
        else:
            if adjustment.available == False:
                await interaction.response.send_message(
                    f"You already skipped pairing on {adjustment_date.strftime('%A %B %d, %Y')}.",
                    ephemeral=True
                )
                return
            adjustment.available = False
        session.commit()

    logger.info(
        f"Skipped pair programming on {adjustment_date.strftime('%A %B %d, %Y')} for user \"{interaction.user.name}\" in guild \"{interaction.guild.name}\", channel \"#{interaction.channel.name}\"."
    )

    msg = f"Successfully skipped pair programming on {adjustment_date.strftime('%A %B %d, %Y')}."
    await interaction.response.send_message(msg, ephemeral=True)


@client.command(
    name="unskip",
    description="Mark yourself as available for pair programming on some date in the future."
)
@discord.app_commands.describe(human_date="A human-readable date like \"tomorrow\" or \"January 1\".")
@discord.app_commands.guild_only()
async def _unskip(
    interaction: discord.Interaction,
    human_date: Optional[str],
):
    assert interaction.guild is not None
    assert isinstance(interaction.channel, discord.TextChannel)

    session = client.make_orm_session()
    with session.begin():
        channel = (
            session.query(PairingChannel)
            .filter(PairingChannel.channel_id == interaction.channel_id)
            .one_or_none()
        )
        if channel is None:
            await interaction.response.send_message(
                f"Pairbot is not active in this channel.",
                ephemeral=True
            )
            return

        schedule = (
            session.query(Schedule)
            .filter(Schedule.channel_id == interaction.channel_id)
            .filter(Schedule.user_id == interaction.user.id)
            .one_or_none()
        )

        if schedule is None or len(schedule.days_available) == 0:
            await interaction.response.send_message(
                f"You are not subscribed to pair programming in #{interaction.channel.name}.",
                ephemeral=True
            )
            return

        if human_date is None:
            adjustment_date = None
            current_weekday = datetime.now().weekday()
            for i in range(0, 7):
                weekday = Weekday((current_weekday + i) % 7)
                if schedule[weekday]:
                    adjustment_date = datetime.now().date() + timedelta(days=i)
                    break

            assert adjustment_date is not None
        else:
            # Clean things up for the parser
            cleaned_date = human_date.lower()
            cleaned_date = cleaned_date.replace("next", "")

            # Try to parse the date
            adjustment_datetime = dateparser.parse(
                cleaned_date,
                settings={
                    "PREFER_DATES_FROM": "future",
                    "RELATIVE_BASE": datetime.now(),
                },
                languages=["en"],
            )
            if adjustment_datetime is None:
                await interaction.response.send_message(
                    f"Could not parse date \"{human_date}\".",
                    ephemeral=True
                )
                return

            adjustment_date = adjustment_datetime.date()
            if adjustment_datetime < datetime.now():
                await interaction.response.send_message(
                    f"Cannot unskip a date in the past: {adjustment_date.strftime('%A %B %d, %Y')}.",
                    ephemeral=True
                )
                return

            weekday = Weekday(adjustment_date.weekday())
            if schedule[weekday] == False:
                await interaction.response.send_message(
                    f"You are not subscribed to pair programming in #{interaction.channel.name} on {weekday}.",
                    ephemeral=True
                )
                return

        adjustment = (
            session.query(ScheduleAdjustment)
            .filter(ScheduleAdjustment.channel_id == interaction.channel_id)
            .filter(ScheduleAdjustment.user_id == interaction.user.id)
            .filter(func.DATE(ScheduleAdjustment.date) == adjustment_date)
            .one_or_none()
        )

        if adjustment is None:
            adjustment = ScheduleAdjustment(
                channel_id=interaction.channel_id,
                user_id=interaction.user.id,
                date=adjustment_date,
                available=True,
            )
            session.add(adjustment)
        else:
            if adjustment.available == True:
                await interaction.response.send_message(
                    f"You already unskipped pairing on {adjustment_date.strftime('%A %B %d, %Y')}.",
                    ephemeral=True
                )
                return
            adjustment.available = True
        session.commit()

    logger.info(
        f"Unskipped pair programming on {adjustment_date.strftime('%A %B %d, %Y')} for user \"{interaction.user.name}\" in guild \"{interaction.guild.name}\", channel \"#{interaction.channel.name}\"."
    )

    msg = f"Successfully unskipped pair programming on {adjustment_date.strftime('%A %B %d, %Y')}."
    await interaction.response.send_message(msg, ephemeral=True)


@client.command(
    name="viewschedule",
    description="View your pair programming schedule."
)
@discord.app_commands.guild_only()
async def _view_schedule(
    interaction: discord.Interaction,
):
    assert interaction.guild is not None

    session = client.make_orm_session()
    with session.begin():
        schedules = (
            session.query(Schedule)
            .filter(Schedule.user_id == interaction.user.id)
            .all()
        )

        adjustments = (
            session.query(ScheduleAdjustment)
            .filter(ScheduleAdjustment.user_id == interaction.user.id)
            .all()
        )

        guild_schedule = {
            interaction.guild.get_channel(schedule.channel_id): [str(day) for day in schedule.days_available]
            for schedule in schedules
        }

        skipped = dict()
        unskipped = dict()

        for adjustment in adjustments:
            channel_name = interaction.guild.get_channel(adjustment.channel_id)
            if adjustment.available == False:
                if channel_name not in skipped:
                    skipped[channel_name] = []
                skipped[channel_name].append(adjustment.date.strftime("%a %b %d"))
            if adjustment.available == True:
                if channel_name not in unskipped:
                    unskipped[channel_name] = []
                unskipped[channel_name].append(adjustment.date.strftime("%a %b %d"))

        if len(guild_schedule) == 0 or sum([len(days) for days in guild_schedule.values()]) == 0:
            msg = "You are not subscribed to pair programming."
        elif len(guild_schedule) == 1:
            channel_name, schedule = guild_schedule.popitem()
            msg = f"You are subscribed to pair programming in #{channel_name} on {', '.join(schedule)}"
            if channel_name in skipped and len(skipped[channel_name]) > 0:
                msg += f" (skipping {', '.join(skipped[channel_name])})"
        else:
            msg = "You are subscribed to pair programming in the following channels:\n"
            for channel_name, schedule in guild_schedule.items():
                msg += f"* #{channel_name}: {', '.join(schedule)}"
                if channel_name in skipped and len(skipped[channel_name]) > 0:
                    msg += f" (skipping {', '.join(skipped[channel_name])})"
                msg += "\n"

    await interaction.response.send_message(msg, ephemeral=True)


@client.command(
    name="pairwith",
    description="Start a pairing session with another channel member."
)
@discord.app_commands.guild_only()
async def _pair_with(
    interaction: discord.Interaction,
    user: discord.Member,
):
    assert interaction.guild is not None
    assert isinstance(interaction.channel, discord.TextChannel)

    if user.id == interaction.user.id:
        await interaction.response.send_message(
            f"You cannot pair with yourself.",
            ephemeral=True
        )
        return

    session = client.make_orm_session()
    with session.begin():
        pairing = (
            session.query(Pairing)
            .filter(or_(
                Pairing.user_1_id == interaction.user.id,
                Pairing.user_2_id == interaction.user.id,
            ))
            .filter(or_(
                Pairing.user_1_id == user.id,
                Pairing.user_2_id == user.id,
            ))
            .one_or_none()
        )

        usernames = sorted([user.name for user in (interaction.user, user)])

        if pairing is None:
            # Make new discord thread
            thread = await interaction.channel.create_thread(
                name=f"{usernames[0]} & {usernames[1]}",
            )

            pairing = Pairing(
                channel_id=interaction.channel.id,
                thread_id=thread.id,
                user_1_id=interaction.user.id,
                user_2_id=user.id,
            )
            session.add(pairing)
            session.commit()
        else:
            thread = interaction.guild.get_thread(pairing.thread_id)
            if thread is None:
                session.delete(pairing)
                session.commit()

                # Make new discord thread
                thread = await interaction.channel.create_thread(
                    name=f"{usernames[0]} & {usernames[1]}",
                )

                pairing = Pairing(
                    channel_id=interaction.channel.id,
                    thread_id=thread.id,
                    user_1_id=interaction.user.id,
                    user_2_id=user.id,
                )
                session.add(pairing)
                session.commit()

        await thread.send(
            f"<@{interaction.user.id}> has started a pairing session with you, <@{user.id}>. Happy pairing! :computer:"
        )
    await interaction.response.send_message(
        f"Successfully created pairing thread with <@{user.id}>",
        ephemeral=True
    )


@discord.ext.tasks.loop(time=config.PAIRING_TIME)
async def make_groups():
    pass


def run():
    client.run(config.DISCORD_BOT_TOKEN)
