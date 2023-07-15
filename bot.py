import json
import logging
import os
import random
import sqlite3
from datetime import datetime
from typing import List

import discord
from discord import app_commands
from discord.ext import tasks
from dotenv import load_dotenv

from db import DB, Timeblock

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
GUILDS_PATH = "data/guilds.json"
DB_PATH = "data/pairing-prod.db"
LOG_FILE = "pairing.log"
SORRY = "Unexpected error."

logging.basicConfig(
    filename=LOG_FILE,
    filemode="a",
    format="%(asctime)s,%(msecs)d %(name)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
    level=logging.DEBUG,
)
logger = logging.getLogger("pairbot")

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)
db = DB(DB_PATH)


def read_guild_to_channel():
    with open(GUILDS_PATH, "r") as f:
        return json.load(f)


# Discord API currently doesn't support variadic arguments
# https://github.com/discord/discord-api-docs/discussions/3286
@tree.command(
    name="subscribe",
    description="Add timeblocks to find a partner for pair programming. \
Matches go out at 8am UTC that day.",
)
@app_commands.describe(
    timeblock="Choose WEEK to get a partner for the whole week (pairs announced Monday UTC)."
)
@app_commands.choices(
    timeblock=[
        app_commands.Choice(name=Timeblock.WEEK.name, value=Timeblock.WEEK.value),
        app_commands.Choice(name=Timeblock.Monday.name, value=Timeblock.Monday.value),
        app_commands.Choice(name=Timeblock.Tuesday.name, value=Timeblock.Tuesday.value),
        app_commands.Choice(
            name=Timeblock.Wednesday.name, value=Timeblock.Wednesday.value
        ),
        app_commands.Choice(
            name=Timeblock.Thursday.name, value=Timeblock.Thursday.value
        ),
        app_commands.Choice(name=Timeblock.Friday.name, value=Timeblock.Friday.value),
        app_commands.Choice(
            name=Timeblock.Saturday.name, value=Timeblock.Saturday.value
        ),
        app_commands.Choice(name=Timeblock.Sunday.name, value=Timeblock.Sunday.value),
    ]
)
async def _subscribe(interaction: discord.Interaction, timeblock: Timeblock):
    try:
        db.insert(interaction.guild_id, interaction.user.id, timeblock)
        timeblocks = db.query_userid(interaction.guild_id, interaction.user.id)
        logger.info(
            f"G:{interaction.guild_id} U:{interaction.user.id} subscribed T:{timeblock.name}."
        )
        msg = (
            f"Your new schedule is `{Timeblock.generate_schedule(timeblocks)}`. "
            f"You can call `/subscribe` again to sign up for more days."
        )
        await interaction.response.send_message(msg, ephemeral=True)
    except sqlite3.IntegrityError:
        logger.info(
            f"G:{interaction.guild_id} U:{interaction.user.id} failed subscribe T:{timeblock.name}."
        )
        msg = (
            f"You are already subscribed to {timeblock}. "
            f"Call `/unsubscribe` to remove a subscription or `/schedule` to view your schedule."
        )
        await interaction.response.send_message(msg, ephemeral=True)
    except Exception as e:
        logger.error(e, exc_info=True)
        await interaction.response.send_message(SORRY, ephemeral=True)


@tree.command(name="unsubscribe", description="Remove timeblocks for pair programming.")
@app_commands.describe(timeblock="Call `/unsubscribe-all` to remove all timeblocks.")
@app_commands.choices(
    timeblock=[
        app_commands.Choice(name=Timeblock.WEEK.name, value=Timeblock.WEEK.value),
        app_commands.Choice(name=Timeblock.Monday.name, value=Timeblock.Monday.value),
        app_commands.Choice(name=Timeblock.Tuesday.name, value=Timeblock.Tuesday.value),
        app_commands.Choice(
            name=Timeblock.Wednesday.name, value=Timeblock.Wednesday.value
        ),
        app_commands.Choice(
            name=Timeblock.Thursday.name, value=Timeblock.Thursday.value
        ),
        app_commands.Choice(name=Timeblock.Friday.name, value=Timeblock.Friday.value),
        app_commands.Choice(
            name=Timeblock.Saturday.name, value=Timeblock.Saturday.value
        ),
        app_commands.Choice(name=Timeblock.Sunday.name, value=Timeblock.Sunday.value),
    ]
)
async def _unsubscribe(interaction: discord.Interaction, timeblock: Timeblock):
    try:
        db.delete(interaction.guild_id, interaction.user.id, timeblock)
        timeblocks = db.query_userid(interaction.guild_id, interaction.user.id)
        logger.info(
            f"G:{interaction.guild_id} U:{interaction.user.id} unsubscribed T:{timeblock.name}."
        )
        msg = f"Your new schedule is `{Timeblock.generate_schedule(timeblocks)}`."
        await interaction.response.send_message(msg, ephemeral=True)
    except Exception as e:
        logger.error(e, exc_info=True)
        await interaction.response.send_message(SORRY, ephemeral=True)


@tree.command(
    name="unsubscribe-all", description="Remove all timeblocks for pair programming."
)
async def _unsubscribe_all(interaction: discord.Interaction):
    try:
        db.unsubscribe(interaction.guild_id, interaction.user.id)
        logger.info(
            f"G:{interaction.guild_id} U:{interaction.user.id} called unsubscribe-all."
        )
        msg = "Your pairing subscriptions have been removed. To rejoin, call `/subscribe` again."
        await interaction.response.send_message(msg, ephemeral=True)
    except Exception as e:
        logger.error(e, exc_info=True)
        await interaction.response.send_message(SORRY, ephemeral=True)


@tree.command(name="schedule", description="View your pairing schedule.")
async def _schedule(interaction: discord.Interaction):
    try:
        timeblocks = db.query_userid(interaction.guild_id, interaction.user.id)
        msg = (
            f"Your current schedule is `{Timeblock.generate_schedule(timeblocks)}`. "
            "You can call `/subscribe` or `/unsubscribe` to modify it."
        )
        await interaction.response.send_message(msg, ephemeral=True)
    except Exception as e:
        logger.error(e, exc_info=True)
        await interaction.response.send_message(SORRY, ephemeral=True)


@tree.command(
    name="set-channel", description="Set a channel for bot messages (admin only)."
)
@app_commands.checks.has_permissions(administrator=True)
async def _set_channel(interaction: discord.Interaction, channel: discord.TextChannel):
    try:
        guild_to_channel = read_guild_to_channel()
        guild_to_channel[str(interaction.guild_id)] = channel.id
        with open(GUILDS_PATH, "w") as f:
            json.dump(guild_to_channel, f)
        logger.info(
            f"G:{interaction.guild_id} U:{interaction.user.id} set-channel C:{channel.id}."
        )
        msg = f"Successfully set bot channel to `{channel.name}`."
        await interaction.response.send_message(msg, ephemeral=True)
    except Exception as e:
        logger.error(e, exc_info=True)
        await interaction.response.send_message(SORRY, ephemeral=True)


@tree.command(
    name="pairwith",
    description="Start an immediate pairing session with another member.",
)
async def _pairwith(interaction: discord.Interaction, user: discord.Member):
    try:
        guild_to_channel = read_guild_to_channel()
        channel_id = guild_to_channel[str(interaction.guild_id)]
        channel = client.get_channel(channel_id)
        users = [interaction.user, user]
        notify_msg = (
            f"<@{interaction.user.id}> has started an on-demand pair with you, <@{user.id}>. "
            "Happy pairing! :computer:"
        )
        await create_group_thread(users, channel, notify_msg)
        logger.info(
            f"G:{interaction.guild_id} C:{channel.id} on-demand paired U:{interaction.user.id} with {user.id}."
        )
        await interaction.response.send_message(
            f"Thread with {user.global_name} created in channel `{channel.name}`.",
            ephemeral=True,
        )
    except Exception as e:
        logger.error(e, exc_info=True)
        await interaction.response.send_message(SORRY, ephemeral=True)


async def dm_user(user: discord.User, msg: str):
    try:
        channel = await user.create_dm()
        await channel.send(msg)
    except Exception as e:
        logger.error(e, exc_info=True)


async def create_group_thread(
    users: List[discord.User], channel: discord.TextChannel, notify_msg: str
):
    # @ notifying users in a private thread invites them
    # so `notify_msg` must notify for this to work
    try:
        title = ", ".join(user.global_name for user in users)
        thread = await channel.create_thread(
            name=f"{title}", auto_archive_duration=10080
        )
        await thread.send(notify_msg)
    except Exception as e:
        logger.error(e, exc_info=True)


async def on_tree_error(
    interaction: discord.Interaction, error: app_commands.AppCommandError
):
    if isinstance(error, app_commands.CommandOnCooldown):
        return await interaction.response.send_message(
            f"Command is currently on cooldown, try again in {error.retry_after:.2f} seconds.",
            ephemeral=True,
        )
    elif isinstance(error, app_commands.MissingPermissions):
        return await interaction.response.send_message(
            "You don't have the permissions to do that.", ephemeral=True
        )
    else:
        raise error


@tasks.loop(hours=1)
async def pairing_cron():
    def should_run():
        now = datetime.utcnow()
        hour = now.time().hour
        return hour == 8

    if should_run():
        now = datetime.utcnow()
        print(now)
        weekday = now.weekday()
        weekday_map = {
            0: Timeblock.Monday,
            1: Timeblock.Tuesday,
            2: Timeblock.Wednesday,
            3: Timeblock.Thursday,
            4: Timeblock.Friday,
            5: Timeblock.Saturday,
            6: Timeblock.Sunday,
        }
        timeblock = weekday_map[weekday]
        for guild in client.guilds:
            await pair(guild.id, timeblock)
            # weekly Monday match
            if weekday == 0:
                await pair(guild.id, Timeblock.WEEK)


async def pair(guild_id: int, timeblock: Timeblock):
    try:
        userids = db.query_timeblock(guild_id, timeblock)
        users = [client.get_user(userid) for userid in userids]
        # Users may leave the server without unsubscribing
        # TODO: listen to that event and drop them from the table
        users = list(filter(None, users))
        logger.info(
            f"Pairing for G:{guild_id} T:{timeblock.name} with {len(users)}/{len(userids)} users."
        )

        if len(users) < 2:
            for user in users:
                logger.info(
                    f"G:{guild_id} T:{timeblock.name} pair failed, dming U:{user.id}."
                )
                msg = (
                    f"Thanks for signing up for pairing this {timeblock}. "
                    "Unfortunately, there was nobody else available this time."
                )
                await dm_user(user, msg)
            return
        guild_to_channel = read_guild_to_channel()
        channel = client.get_channel(guild_to_channel[str(guild_id)])

        random.shuffle(users)
        groups = [users[i :: len(users) // 2] for i in range(len(users) // 2)]
        for group in groups:
            notify_msg = ", ".join(f"<@{user.id}>" for user in users)
            notify_msg = f"{msg}: you've been matched together for this {timeblock}. Happy pairing! :computer:"
            await create_group_thread(group, channel, notify_msg)
            logger.info(
                f"G:{guild_id} C:{channel.id} paired U:{[user.id for user in users]}."
            )
        await channel.send(
            f"It's 8am UTC: {len(groups)} pairing(s) have been sent out for this {timeblock}!"
        )
    except Exception as e:
        logger.error(e, exc_info=True)


def local_setup():
    try:
        read_guild_to_channel()
    except Exception:
        with open(GUILDS_PATH, "w") as f:
            json.dump({}, f)


@client.event
async def on_ready():
    local_setup()
    await client.wait_until_ready()
    tree.on_error = on_tree_error
    for guild in client.guilds:
        tree.copy_global_to(guild=guild)
        await tree.sync(guild=guild)
    print("Code sync complete!")
    pairing_cron.start()
    print("Starting cron loop...")
    logger.info("Bot started.")


client.run(BOT_TOKEN)
