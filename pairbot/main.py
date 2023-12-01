import pdb

from typing import (
    Any,
    Optional,
)

import random
from datetime import (
    date,
    datetime,
    timedelta,
)
import dateparser

import discord
import discord.ext.tasks

import sqlalchemy
import sqlalchemy.orm

from . import config

from .app import DiscordApp
from .models import (
    PairingChannel,
    Schedule,
    Skip,
    Weekday,
    Pairing,
)

app = DiscordApp(intents=discord.Intents.all())

db_engine = sqlalchemy.create_engine(config.DATABASE_URL)
Session = sqlalchemy.orm.sessionmaker(db_engine)


# Utility functions


def get_active_pairing_channel(
    session: sqlalchemy.orm.Session,
    interaction: discord.Interaction,
) -> Optional[PairingChannel]:
    if interaction.channel is None: return None
    return (
        session.query(PairingChannel)
        .filter(PairingChannel.channel_id == interaction.channel.id)
        .one_or_none()
    )


def get_user_schedule(
    session: sqlalchemy.orm.Session,
    interaction: discord.Interaction,
) -> Optional[Schedule]:
    if interaction.channel is None: return None
    return (
        session.query(Schedule)
        .filter(Schedule.channel_id == interaction.channel_id)
        .filter(Schedule.user_id == interaction.user.id)
        .one_or_none()
    )


def make_user_schedule(
    session: sqlalchemy.orm.Session,
    interaction: discord.Interaction,
) -> Schedule:
    assert interaction.channel is not None
    schedule = Schedule(
        channel_id = interaction.channel_id,
        user_id = interaction.user.id,
    )
    session.add(schedule)
    app.logger.info("Created new schedule.")
    return schedule


def parse_human_readable_date(maybe_a_date: str) -> Optional[date]:
    # Preprocess with some ad-hoc rules
    maybe_a_date = (
        maybe_a_date
        .lower()
        .replace("next", "")
    )
    parsed_date = dateparser.parse(
        maybe_a_date,
        settings={
            "PREFER_DATES_FROM": "future",
            "RELATIVE_BASE": datetime.now(),
        },
        languages=["en"],
    )
    if parsed_date is not None:
        return parsed_date.date()


def get_next_scheduled_date(schedule: Schedule) -> Optional[date]:
    current_weekday = datetime.now().weekday()
    for i in range(0, 7):
        next_weekday = Weekday((current_weekday + i) % 7)
        if schedule.is_available_on(next_weekday):
            return datetime.now().date() + timedelta(days=i)
    return None


def format_date(d: date):
    return d.strftime('%A %B %d, %Y')


def get_skip(
    session: sqlalchemy.orm.Session,
    interaction: discord.Interaction,
    d: date,
) -> Optional[Skip]:
    return (
        session.query(Skip)
        .filter(Skip.channel_id == interaction.channel_id)
        .filter(Skip.user_id == interaction.user.id)
        .filter(sqlalchemy.func.DATE(Skip.date) == d)
        .one_or_none()
    )


def make_skip(
    session: sqlalchemy.orm.Session,
    interaction: discord.Interaction,
    d: date,
) -> Skip:
    skip = Skip(
        channel_id=interaction.channel_id,
        user_id=interaction.user.id,
        date=d,
    )
    session.add(skip)
    app.logger.info("Created new skip.")
    return skip


async def fail_on_inactive_channel(
    session: sqlalchemy.orm.Session,
    interaction: discord.Interaction,
) -> bool:
    channel = get_active_pairing_channel(session, interaction)
    if channel is None:
        app.logger.info("Pairbot not active in channel.")
        await interaction.response.send_message(
            "Pairbot is not active in this channel.",
            ephemeral=True
        )
        return True
    else:
        return False


async def fail_on_existing_subscription(
    interaction: discord.Interaction,
    schedule: Schedule,
    weekday: Optional[Weekday],
) -> bool:
    assert isinstance(interaction.channel, discord.TextChannel)
    if weekday is not None and schedule.is_available_on(weekday):
        app.logger.info("Already subscribed on %s", weekday)
        await interaction.response.send_message(
            "You are already subscribed to pair programming on %s in #%s." % (
                weekday,
                interaction.channel.name),
            ephemeral=True
        )
        return True
    elif schedule.num_days_available() == 7:
        app.logger.info("Already subscribed daily")
        await interaction.response.send_message(
            "You are already subscribed to daily pair programming in #%s." % interaction.channel.name,
            ephemeral=True
        )
        return True
    return False


async def fail_on_nonexistent_subscription(
    interaction: discord.Interaction,
    schedule: Optional[Schedule],
    weekday: Optional[Weekday],
) -> bool:
    assert isinstance(interaction.channel, discord.TextChannel)
    if schedule is not None and weekday is not None  and not schedule.is_available_on(weekday):
        app.logger.info("Not subscribed on %s", weekday)
        await interaction.response.send_message(
            "You are not subscribed to pair programming on %s in #%s." % (
                weekday,
                interaction.channel.name),
            ephemeral=True
        )
        return True
    elif schedule is None or schedule.num_days_available() == 0:
        await interaction.response.send_message(
            ("You are not subscribed to pair programming in #%s." % interaction.channel.name),
            ephemeral=True
        )
        return True
    return False


def get_pairing(
    session: sqlalchemy.orm.Session,
    interaction: discord.Interaction,
    user_1: discord.User | discord.Member,
    user_2: discord.Member
) -> Optional[Pairing]:
    return (
        session.query(Pairing)
        .filter(sqlalchemy.or_(
            Pairing.user_1_id == user_1.id,
            Pairing.user_2_id == user_1.id,
        ))
        .filter(sqlalchemy.or_(
            Pairing.user_1_id == user_2.id,
            Pairing.user_2_id == user_2.id,
        ))
        .one_or_none()
    )


# Slash commands


@app.command(
    name="addpairbot",
    description="Add Pairbot to the current channel.",
)
@discord.app_commands.guild_only()
@discord.app_commands.checks.has_permissions(administrator=True)
async def _add_pairbot(interaction: discord.Interaction):
    assert interaction.guild is not None
    assert isinstance(interaction.channel, discord.TextChannel)

    with Session.begin() as session:
        channel = (
            session.query(PairingChannel)
            .filter(PairingChannel.channel_id == interaction.channel_id)
            .one_or_none()
        )

        if channel is not None:
            app.logger.info("Pairbot is already added.")
            await interaction.response.send_message(
                "Pairbot is already added to \"#%s\"." % interaction.channel.name,
                ephemeral=True,
            )
            return

        channel = PairingChannel(
            guild_id = interaction.guild.id,
            channel_id = interaction.channel.id,
            leetcode_integration = False, # TODO
        )
        session.add(channel)

        app.logger.info("Added Pairbot.")

        await interaction.response.send_message(
            "Added Pairbot to \"#%s\"." % interaction.channel.name,
            ephemeral=True,
        )


@app.command(
    name="removepairbot",
    description="Remove Pairbot from the current channel."
)
@discord.app_commands.guild_only()
@discord.app_commands.checks.has_permissions(administrator=True)
async def _remove_pairbot(interaction: discord.Interaction):
    assert interaction.guild is not None
    assert isinstance(interaction.channel, discord.TextChannel)

    with Session.begin() as session:
        channel = (
            session.query(PairingChannel)
            .filter(PairingChannel.channel_id == interaction.channel_id)
            .one_or_none()
        )

        if channel is None:
            app.logger.info("Pairbot is not added.")
            await interaction.response.send_message(
                "Pairbot is not added to \"#%s\"." % interaction.channel.name,
                ephemeral=True,
            )
            return

        session.delete(channel)

        app.logger.info("Removed pairbot.")

        await interaction.response.send_message(
            "Removed Pairbot from \"#%s\"." % interaction.channel.name,
            ephemeral=True,
        )


@app.command(
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

    with Session.begin() as session:
        if fail_on_inactive_channel(session, interaction):
            return

        schedule = get_user_schedule(session, interaction)

        if schedule is None:
            schedule = make_user_schedule(session, interaction)
        else:
            app.logger.info("Found existing schedule")

        if fail_on_existing_subscription(interaction, schedule, weekday):
            return

        if weekday is not None:
            schedule.set_availability_on(weekday, True)
            app.logger.info("Subscribed to pair programming on %s", weekday)
            await interaction.response.send_message(
                "Successfully subscribed to pair programming on %s in #%s." % (weekday, interaction.channel.name),
                ephemeral=True
            )
        else:
            schedule.set_availability_every_day(True)
            app.logger.info("Subscribed to daily pair programming")
            await interaction.response.send_message(
                "Successfully subscribed to daily pair programming in #%s." % interaction.channel.name,
                ephemeral=True
            )


@app.command(
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

    with Session.begin() as session:
        if fail_on_inactive_channel(session, interaction):
            return

        schedule = get_user_schedule(session, interaction)

        if schedule is None or schedule.num_days_available() == 0:
            await interaction.response.send_message(
                ("You are already not subscribed to pair programming in #%s." % interaction.channel.name),
                ephemeral=True
            )
            return

        if fail_on_nonexistent_subscription(interaction, schedule, weekday):
            return

        if weekday is not None:
            schedule.set_availability_on(weekday, False)
            await interaction.response.send_message(
                ("Successfully unsubscribed from pair programming on %s in #%s." % weekday, interaction.channel.name),
                ephemeral=True
            )
        else:
            schedule.set_availability_every_day(False)
            await interaction.response.send_message(
                ("Successfully unsubscribed from all pair programming in #%s." % interaction.channel.name),
                ephemeral=True
            )


@app.command(
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

    with Session.begin() as session:
        if fail_on_inactive_channel(session, interaction):
            return

        schedule = get_user_schedule(session, interaction)

        if fail_on_nonexistent_subscription(interaction, schedule, None):
            return

        assert schedule is not None

        if human_date is None:
            skipped_date = get_next_scheduled_date(schedule)
            assert skipped_date is not None
        else:
            skipped_date = parse_human_readable_date(human_date)
            if skipped_date is None:
                await interaction.response.send_message(
                    "Could not parse date \"%s\"." % date,
                    ephemeral=True
                )
                return

            if skipped_date < datetime.now().date():
                await interaction.response.send_message(
                    "Cannot skip a date in the past: %s." % format_date(skipped_date),
                    ephemeral=True
                )
                return

            skipped_weekday = Weekday(skipped_date.weekday())

            if fail_on_nonexistent_subscription(interaction, schedule, skipped_weekday):
                return

        skip = get_skip(session, interaction, skipped_date)

        if skip is None:
            skip = make_skip(session, interaction, skipped_date)
        else:
            await interaction.response.send_message(
                "You already skipped pairing on %s." % format_date(skipped_date),
                ephemeral=True
            )
            return

    app.logger.info("Skipped pair programming on %s" % format_date(skipped_date))
    await interaction.response.send_message(
        "Successfully skipped pair programming on %s" % format_date(skipped_date),
        ephemeral=True
    )


@app.command(
    name="unskip",
    description="Unskip a skipped pairing session."
)
@discord.app_commands.describe(human_date="A human-readable date like \"tomorrow\" or \"January 1\".")
@discord.app_commands.guild_only()
async def _unskip(
    interaction: discord.Interaction,
    human_date: Optional[str],
):
    assert interaction.guild is not None
    assert isinstance(interaction.channel, discord.TextChannel)

    with Session.begin() as session:
        if fail_on_inactive_channel(session, interaction):
            return

        schedule = get_user_schedule(session, interaction)

        if fail_on_nonexistent_subscription(interaction, schedule, None):
            return
        assert schedule is not None

        if human_date is None:
            unskipped_date = get_next_scheduled_date(schedule)
            assert unskipped_date is not None
        else:
            unskipped_date = parse_human_readable_date(human_date)
            if unskipped_date is None:
                await interaction.response.send_message(
                    "Could not parse date \"%s\"." % date,
                    ephemeral=True
                )
                return

            if unskipped_date < datetime.now().date():
                await interaction.response.send_message(
                    "Cannot unskip a date in the past: %s." % format_date(unskipped_date),
                    ephemeral=True
                )
                return

            unskipped_weekday = Weekday(unskipped_date.weekday())

            if fail_on_nonexistent_subscription(interaction, schedule, unskipped_weekday):
                return

        skip = get_skip(session, interaction, unskipped_date)

        if skip is None:
            await interaction.response.send_message(
                "You did not skip pair programming on %s." % format_date(unskipped_date),
                ephemeral=True
            )
            return
        else:
            session.delete(skip)

    app.logger.info("Unskipped pair programming on %s" % format_date(unskipped_date))
    await interaction.response.send_message(
        "Successfully unskipped pair programming on %s" % format_date(unskipped_date),
        ephemeral=True
    )


@app.command(
    name="viewschedule",
    description="View your pair programming schedule."
)
@discord.app_commands.guild_only()
async def _view_schedule(
    interaction: discord.Interaction,
):
    assert interaction.guild is not None
    assert isinstance(interaction.channel, discord.TextChannel)

    with Session.begin() as session:
        if fail_on_inactive_channel(session, interaction):
            return

        all_schedules = (
            session.query(Schedule)
            .filter(Schedule.user_id == interaction.user.id)
            .all()
        )

        all_skips = (
            session.query(Skip)
            .filter(Skip.user_id == interaction.user.id)
            .filter(sqlalchemy.func.DATE(Skip.date) >= datetime.now())
            .all()
        )

        grouped_schedules: dict[str, list[str]] = dict()
        grouped_skips: dict[str, list[str]] = dict()

        for schedule in all_schedules:
            channel = interaction.guild.get_channel(schedule.channel_id)
            if channel is None: continue
            channel_name = channel.name
            grouped_schedules[channel_name] = list(map(str, schedule.days_available()))

        for skip in all_skips:
            channel = interaction.guild.get_channel(skip.channel_id)
            if channel is None: continue
            channel_name = channel.name
            if channel_name not in grouped_skips:
                grouped_skips[channel_name] = []
            grouped_skips[channel_name].append(skip.date.strftime("%a %b %d"))

        if len(all_schedules) == 0 or sum([len(days) for days in grouped_schedules.values()]) == 0:
            await interaction.response.send_message(
                "You are not subscribed to pair programming in any channel.",
                ephemeral=True
            )
            return

        if len(grouped_schedules) == 1:
            channel_name, weekdays = grouped_schedules.popitem()
            if len(weekdays) == 7:
                await interaction.response.send_message(
                    "You are subscribed to pair programming in #%s every day%s" % (
                        channel_name,
                        " (skipping " + ", ".join(grouped_skips[channel_name]) + ")" if channel_name in grouped_skips else ""
                    ),
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    "You are subscribed to pair programming in #%s on %s%s" % (
                        channel_name,
                        ", ".join(weekdays),
                        " (skipping " + ", ".join(grouped_skips[channel_name]) + ")" if channel_name in grouped_skips else ""
                    ),
                    ephemeral=True
                )
            return

        response = "You are subscribed to pair programming in the following channels:\n"
        for channel_name, weekdays in grouped_schedules.items():
            response += "* #%s: %s%s\n" % (
                channel_name,
                ", ".join(weekdays),
                "skipping " + ", ".join(grouped_skips[channel_name]) if channel_name in grouped_skips else ""
            )
        await interaction.response.send_message(response, ephemeral=True)



@app.command(
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

    with Session.begin() as session:
        if fail_on_inactive_channel(session, interaction):
            return

        pairing = get_pairing(session, interaction, interaction.user, user)

        usernames = sorted([user.name for user in (interaction.user, user)])

        if pairing is None:
            # Make new discord thread
            thread = await interaction.channel.create_thread(
                name=f"{usernames[0]} & {usernames[1]}",
            )

            pairing = Pairing(
                channel_id=interaction.channel_id,
                user_1_id=interaction.user.id,
                user_2_id=user.id,
            )
            session.add(pairing)
        else:
            thread = interaction.guild.get_thread(pairing.thread_id)
            if thread is None:
                session.delete(pairing)

                # Make new discord thread
                thread = await interaction.channel.create_thread(
                    name=f"{usernames[0]} & {usernames[1]}",
                )

                pairing = Pairing(
                    channel_id=interaction.channel_id,
                    user_1_id=interaction.user.id,
                    user_2_id=user.id,
                )
                session.add(pairing)

        await thread.send(
            f"<@{interaction.user.id}> has started a pairing session with you, <@{user.id}>. Happy pairing! :computer:"
        )
    await interaction.response.send_message(
        f"Successfully created pairing thread with <@{user.id}>",
        ephemeral=True
    )


@discord.ext.tasks.loop(time=config.PAIRING_TIME)
async def make_groups():
    app.logger.info("Creating random groups.")

    with Session.begin() as session:
        for guild in app.client.guilds:
            channels = (
                session.query(PairingChannel)
                .filter(PairingChannel.guild_id == guild.id)
                .all()
            )
            for pairing_channel in channels:
                channel = app.client.get_channel(pairing_channel.channel_id)
                if channel is None:
                    session.delete(pairing_channel)
                    app.logger.info("Pairing channel is gone :(")
                    continue
                assert isinstance(channel, discord.TextChannel)
                schedules = (
                    session.query(Schedule)
                    .filter(Schedule.channel_id == channel.id)
                    .all()
                )

                todays_users = [
                    guild.get_member(schedule.user_id)
                    for schedule in schedules
                    if schedule.is_available_on(Weekday(datetime.now().weekday()))
                ]

                if len(todays_users) < 2:
                    app.logger.info("Not enough users to make groups.")

                random.shuffle(todays_users)

                groups = []
                if len(todays_users) % 2 == 1:
                    pair = (
                        todays_users.pop(),
                        todays_users.pop(),
                        todays_users.pop(),
                    )
                    groups.append(pair)

                while len(todays_users) > 0:
                    pair = (
                        todays_users.pop(),
                        todays_users.pop(),
                        None,
                    )
                    groups.append(pair)

                for group in groups:
                    usernames = sorted([user.name for user in group])
                    user1, user2, user3 = group

                    # TODO find existing pairing and get thread
                    pairing = Pairing(
                        channel_id=channel.id,
                        user_1_id=user1.id,
                        user_2_id=user2.id,
                        user_3_id=user3.id if user3 is not None else None,
                    )
                    session.add(pairing)

                    # Make new discord thread
                    thread = await channel.create_thread(
                        name=" & ".join(usernames)
                    )

                    await thread.send(
                        " ".join("<@%d>" % (user.id for user in group if user is not None))
                    )
                    await thread.send(
                        "You have been matched together. Happy pairing! :computer:"
                    )

                app.logger.info("Send out pairings.")


def run():
    app.run(config.DISCORD_BOT_TOKEN)
