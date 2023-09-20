import json
import logging
import os
import random
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List

import discord
from discord import app_commands
from discord.ext import tasks
from dotenv import load_dotenv

from db import PairingsDB, ScheduleDB, Timeblock, LeetCodeDB
from utils import get_user_name, parse_args, read_guild_to_channel, get_random_leetcode_problem

load_dotenv()
args = parse_args()
if args.dev:
    print("Running in dev mode.")
    BOT_TOKEN = os.getenv("BOT_TOKEN_DEV")
    DATA_DIR = "data"
    GUILDS_PATH = f"{DATA_DIR}/guilds-dev.json"
    SCHEDULE_DB_PATH = f"{DATA_DIR}/schedule-dev.db"
    PAIRINGS_DB_PATH = f"{DATA_DIR}/pairings-dev.db"
    LEETCODE_DB_PATH = f"{DATA_DIR}/leetcode-dev.db"
    LOG_FILE = "pairbot-dev.log"
else:
    print("Running in prod mode.")
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    DATA_DIR = "data"
    GUILDS_PATH = f"{DATA_DIR}/guilds.json"
    SCHEDULE_DB_PATH = f"{DATA_DIR}/schedule.db"
    PAIRINGS_DB_PATH = f"{DATA_DIR}/pairings.db"
    LEETCODE_DB_PATH = f"{DATA_DIR}/leetcode.db"
    LOG_FILE = "pairbot.log"
SORRY = "Unexpected error."
Path(DATA_DIR).mkdir(parents=True, exist_ok=True)

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
db = ScheduleDB(SCHEDULE_DB_PATH)
pairings_db = PairingsDB(PAIRINGS_DB_PATH)
leetcode_db = LeetCodeDB(LEETCODE_DB_PATH)

# Discord API currently doesn't support variadic arguments
# https://github.com/discord/discord-api-docs/discussions/3286
@tree.command(
    name="leetcode", 
    description="Get a random LeetCode problem based on difficulty."
)
@app_commands.describe(difficulty="Choose a difficulty level for the LeetCode problem.")
@app_commands.choices(
    difficulty=[
        app_commands.Choice(name="Easy", value="Easy"),
        app_commands.Choice(name="Medium", value="Medium"),
        app_commands.Choice(name="Hard", value="Hard"),
        app_commands.Choice(name="Any difficulty", value="Any"),
    ]
)
async def _leetcode(interaction: discord.Interaction, difficulty: str):
    try:
        problem = get_random_leetcode_problem(difficulty)
        message = f"Here's a {difficulty} LeetCode problem: {problem['title']} - {problem['url']}"
        await interaction.response.send_message(message, ephemeral=True)
    except Exception as e:
        logger.error(f"Error fetching LeetCode problem: {e}", exc_info=True)
        await interaction.response.send_message("Sorry, there was an error fetching the problem.", ephemeral=True)    

@tree.command(
    name="leetcode-subscribe",
    description="Subscribe to receive a LeetCode problem based on timeblock and difficulty."
)
@app_commands.describe(
    timeblock="Choose WEEK to get a partner for the whole week (pairs announced Monday UTC).",
    difficulty="Choose a difficulty level for the LeetCode problem."
)
@app_commands.choices(
    timeblock=[
        app_commands.Choice(name=Timeblock.WEEK.name, value=Timeblock.WEEK.value),
        app_commands.Choice(name=Timeblock.Monday.name, value=Timeblock.Monday.value),
        app_commands.Choice(name=Timeblock.Tuesday.name, value=Timeblock.Tuesday.value),
        app_commands.Choice(name=Timeblock.Wednesday.name, value=Timeblock.Wednesday.value),
        app_commands.Choice(name=Timeblock.Thursday.name, value=Timeblock.Thursday.value),
        app_commands.Choice(name=Timeblock.Friday.name, value=Timeblock.Friday.value),
        app_commands.Choice(name=Timeblock.Saturday.name, value=Timeblock.Saturday.value),
        app_commands.Choice(name=Timeblock.Sunday.name, value=Timeblock.Sunday.value),
    ],
    difficulty=[
        app_commands.Choice(name="Easy", value="Easy"),
        app_commands.Choice(name="Medium", value="Medium"),
        app_commands.Choice(name="Hard", value="Hard"),
        app_commands.Choice(name="Any difficulty", value="Any"),
    ]
)
async def _leetcode_subscribe(interaction: discord.Interaction, timeblock: Timeblock, difficulty: str):
    try:
        leetcode_db.insert(interaction.guild_id, interaction.user.id, timeblock, difficulty)
        await interaction.response.send_message(f"Subscribed to {timeblock} for {difficulty} problems! You can call `/leetcode-subscribe` again to sign up for more days.", ephemeral=True)
    except sqlite3.IntegrityError:
        await interaction.response.send_message("You're already subscribed to this timeblock and difficulty.", ephemeral=True)
    except Exception as e:
        logger.error(e, exc_info=True)
        await interaction.response.send_message(SORRY, ephemeral=True)

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
        app_commands.Choice(name=Timeblock.Wednesday.name, value=Timeblock.Wednesday.value),
        app_commands.Choice(name=Timeblock.Thursday.name, value=Timeblock.Thursday.value),
        app_commands.Choice(name=Timeblock.Friday.name, value=Timeblock.Friday.value),
        app_commands.Choice(name=Timeblock.Saturday.name, value=Timeblock.Saturday.value),
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
    except sqlite3.IntegrityError as e:
        logger.info(
            f"G:{interaction.guild_id} U:{interaction.user.id} failed subscribe T:{timeblock.name}."
        )
        logger.warning(e, exc_info=True)
        msg = (
            f"You are already subscribed to {timeblock}. "
            f"Call `/unsubscribe` to remove a subscription or `/schedule` to view your schedule."
        )
        await interaction.response.send_message(msg, ephemeral=True)
    except Exception as e:
        logger.error(e, exc_info=True)
        await interaction.response.send_message(SORRY, ephemeral=True)


@tree.command(name="unsubscribe", description="Remove timeblocks for pair programming and LeetCode problems.")
@app_commands.describe(timeblock="Call `/unsubscribe-all` to remove all timeblocks.")
@app_commands.choices(
    timeblock=[
        app_commands.Choice(name=Timeblock.WEEK.name, value=Timeblock.WEEK.value),
        app_commands.Choice(name=Timeblock.Monday.name, value=Timeblock.Monday.value),
        app_commands.Choice(name=Timeblock.Tuesday.name, value=Timeblock.Tuesday.value),
        app_commands.Choice(name=Timeblock.Wednesday.name, value=Timeblock.Wednesday.value),
        app_commands.Choice(name=Timeblock.Thursday.name, value=Timeblock.Thursday.value),
        app_commands.Choice(name=Timeblock.Friday.name, value=Timeblock.Friday.value),
        app_commands.Choice(name=Timeblock.Saturday.name, value=Timeblock.Saturday.value),
        app_commands.Choice(name=Timeblock.Sunday.name, value=Timeblock.Sunday.value),
    ]
)
async def _unsubscribe(interaction: discord.Interaction, timeblock: Timeblock):
    try:
        db.delete(interaction.guild_id, interaction.user.id, timeblock)
        logger.info(
            f"G:{interaction.guild_id} U:{interaction.user.id} unsubscribed T:{timeblock.name}."
        )
        leetcode_db.delete(interaction.guild_id, interaction.user.id, timeblock)
        logger.info(
            f"G:{interaction.guild_id} U:{interaction.user.id} unsubscribed from LeetCode T:{timeblock.name}."
        )
        pairing_timeblocks = db.query_userid(interaction.guild_id, interaction.user.id)
        pairing_schedule = Timeblock.generate_schedule(pairing_timeblocks)
        
        leetcode_timeblocks_tuples = leetcode_db.query_userid(interaction.guild_id, interaction.user.id)
        leetcode_schedule_list = [f"{Timeblock(item[0]).name} ({item[1]})" for item in leetcode_timeblocks_tuples]
        leetcode_schedule = ', '.join(leetcode_schedule_list)

        msg = (
            f"Your new pairing schedule is `{pairing_schedule}`.\n"
            f"Your new LeetCode schedule is `{leetcode_schedule}`."
        )
        await interaction.response.send_message(msg, ephemeral=True)
    except Exception as e:
        logger.error(e, exc_info=True)
        await interaction.response.send_message(SORRY, ephemeral=True)  

@tree.command(
    name="unsubscribe-all", description="Remove all timeblocks for pair programming and LeetCode problems."
)
async def _unsubscribe_all(interaction: discord.Interaction):
    try:
        db.unsubscribe(interaction.guild_id, interaction.user.id)
        logger.info(
            f"G:{interaction.guild_id} U:{interaction.user.id} called unsubscribe-all."
        )
        msg = "Your pairing subscriptions have been removed. To rejoin, call `/subscribe` or `/leetcode-subscribe` again."
        await interaction.response.send_message(msg, ephemeral=True)
    except Exception as e:
        logger.error(e, exc_info=True)
        await interaction.response.send_message(SORRY, ephemeral=True)
    try:
        leetcode_db.unsubscribe(interaction.guild_id, interaction.user.id)
    except Exception as e:
        logger.error(e, exc_info=True)

@tree.command(name="schedule", description="View your pairing schedule.")
async def _schedule(interaction: discord.Interaction):
    try:
        pairing_timeblocks = db.query_userid(interaction.guild_id, interaction.user.id)
        pairing_schedule = Timeblock.generate_schedule(pairing_timeblocks)
        
        leetcode_timeblocks_tuples = leetcode_db.query_userid(interaction.guild_id, interaction.user.id)
        leetcode_schedule_list = [f"{Timeblock(item[0]).name} ({item[1]})" for item in leetcode_timeblocks_tuples]
        #leetcode_timeblocks = [Timeblock(item[0]) for item in leetcode_timeblocks_tuples]
        leetcode_schedule = ', '.join(leetcode_schedule_list)

        logger.info(
            f"G:{interaction.guild_id} U:{interaction.user.id} pairing schedule {pairing_schedule} and LeetCode schedule {leetcode_schedule}."
        )
        msg = (
            f"Your current pairing schedule is `{pairing_schedule}` .\n"
            f"Your LeetCode schedule is `{leetcode_schedule}`.\n "
            "You can call `/subscribe`, `/leetcode-subscribe` or `/unsubscribe` to modify it."
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
        guild_to_channel = read_guild_to_channel(GUILDS_PATH)
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
        guild_to_channel = read_guild_to_channel(GUILDS_PATH)
        channel_id = guild_to_channel[str(interaction.guild_id)]
        channel = client.get_channel(channel_id)
        users = [interaction.user, user]
        notify_msg = (
            f"<@{interaction.user.id}> has started an on-demand pair with you, <@{user.id}>. "
            "Happy pairing! :computer:"
        )
        await create_group_thread(interaction.guild_id, users, channel, notify_msg)
        logger.info(
            f"G:{interaction.guild_id} C:{channel.id} on-demand paired U:{interaction.user.id} with {user.id}."
        )
        await interaction.response.send_message(
            f"Thread with {get_user_name(user)} created in channel `{channel.name}`.",
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
    guild_id: int,
    users: List[discord.User],
    channel: discord.TextChannel,
    notify_msg: str,
):
    # @ notifying users in a private thread invites them
    # so `notify_msg` must notify for this to work
    userids = [user.id for user in users]
    thread_id = pairings_db.query_userids(guild_id, userids, channel.id)
    thread = None
    if thread_id is not None:
        logger.debug(f"Found existing thread {thread_id} for G:{guild_id} U:{userids}")
        try:
            guild = client.get_guild(guild_id)
            thread = await guild.fetch_channel(thread_id)
        except discord.errors.NotFound:
            logger.debug(f"Couldn't fetch thread {thread_id}, maybe deleted?")
            pairings_db.delete(guild_id, userids, channel.id, thread_id)
    if thread is None:
        title = ", ".join(get_user_name(user) for user in users)
        thread = await channel.create_thread(
            name=f"{title}", auto_archive_duration=10080
        )
        logger.debug(f"Created new thread {thread.id} for G:{guild_id} U:{userids}")
        pairings_db.insert(guild_id, userids, channel.id, thread.id)
    else:
        logger.debug(f"Found existing thread {thread_id} for G:{guild_id} U:{userids}")
        guild = client.get_guild(guild_id)
        thread = await guild.fetch_channel(thread_id)
    await thread.send(notify_msg)


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
        logger.debug(f"Checking pairing job at UTC:{now}.")
        return hour == 8

    if should_run():
        await run_pairing()


async def run_pairing():
    now = datetime.utcnow()
    print(now)
    logger.debug(f"Running pairing job at UTC:{now}.")
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
        guild_to_channel = read_guild_to_channel(GUILDS_PATH)
        channel = client.get_channel(guild_to_channel[str(guild_id)])
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
            await channel.send(
                f"Not enough signups this {timeblock}. Try `/subscribe` to sign up!"
            )
            return

        random.shuffle(users)
        groups = [users[i :: len(users) // 2] for i in range(len(users) // 2)]
        for group in groups:
            notify_msg = ", ".join(f"<@{user.id}>" for user in group)
            notify_msg = f"{notify_msg}: you've been matched together for this {timeblock}. Happy pairing! :computer:"
            await create_group_thread(guild_id, group, channel, notify_msg)
            logger.info(
                f"G:{guild_id} C:{channel.id} paired U:{[user.id for user in group]}."
            )
        await channel.send(
            f"Pairings for {len(users)} users have been sent out for this {timeblock}. Try `/subscribe` to sign up!"
        )
    except Exception as e:
        logger.error(e, exc_info=True)


def local_setup():
    try:
        read_guild_to_channel(GUILDS_PATH)
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