import sqlite3
from contextlib import closing
from enum import Enum, auto
from typing import List


class Timeblock(Enum):
    WEEK = auto()
    Monday = auto()
    Tuesday = auto()
    Wednesday = auto()
    Thursday = auto()
    Friday = auto()
    Saturday = auto()
    Sunday = auto()

    def __str__(self):
        return self.name

    @staticmethod
    def generate_schedule(timeblocks: List["Timeblock"]) -> str:
        return f"{[str(block) for block in sorted(timeblocks, key=lambda block: block.value)]}"


class DB:
    def __init__(self, path: str) -> None:
        self.db = path
        self.con = sqlite3.connect(self.db)
        self._setup()

    def _setup(self) -> None:
        with closing(self.con.cursor()) as cur:
            cur.execute(
                "CREATE TABLE IF NOT EXISTS users (guildid INTEGER, userid INTEGER, timeblock INTEGER, "
                "UNIQUE (guildid, userid, timeblock))"
            )
            self.con.commit()

    def insert(self, guild_id: int, user_id: int, timeblock: Timeblock) -> None:
        with closing(self.con.cursor()) as cur:
            cur.execute(
                "INSERT INTO users VALUES (?, ?, ?)",
                (guild_id, user_id, timeblock.value),
            )
            self.con.commit()

    def delete(self, guild_id: int, user_id: int, timeblock: Timeblock) -> None:
        with closing(self.con.cursor()) as cur:
            cur.execute(
                "DELETE from users WHERE guildid=? and userid=? and timeblock=?",
                (guild_id, user_id, timeblock.value),
            )
            self.con.commit()

    def unsubscribe(self, guild_id: int, user_id: int) -> None:
        with closing(self.con.cursor()) as cur:
            cur.execute(
                "DELETE FROM users WHERE guildid=? and userid=?", (guild_id, user_id)
            )
            self.con.commit()

    def query_timeblock(self, guild_id: int, timeblock: Timeblock) -> List[int]:
        with closing(self.con.cursor()) as cur:
            res = cur.execute(
                "SELECT userid FROM users WHERE guildid=? and timeblock=?",
                (guild_id, timeblock.value),
            )
            userids = list(map(lambda x: x[0], res.fetchall()))
            return userids

    def query_userid(self, guild_id: int, user_id: int) -> List[Timeblock]:
        with closing(self.con.cursor()) as cur:
            res = cur.execute(
                "SELECT timeblock FROM users WHERE guildid=? and userid=?",
                (guild_id, user_id),
            )
            timeblocks = list(map(lambda x: Timeblock(x[0]), res.fetchall()))
            return timeblocks
