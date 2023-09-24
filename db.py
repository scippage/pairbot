import sqlite3
from contextlib import closing
from enum import Enum, auto
from typing import List, Optional


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

    def generate_leetcode_schedule(tuples: List[tuple]) -> str:
        sorted_tuples = sorted(
            tuples, key=lambda tuple: (Timeblock(tuple[0]).value, tuple[1])
        )
        return ", ".join(
            [f"{Timeblock(item[0]).name} ({item[1]})" for item in sorted_tuples]
        )


class LeetcodeDifficulty(Enum):
    Easy = "Easy"
    Medium = "Medium"
    Hard = "Hard"
    Any = "Any Difficulty"

    def __str__(self):
        return self.name


class ScheduleDB:
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


class PairingsDB:
    def __init__(self, path: str) -> None:
        self.db = path
        self.con = sqlite3.connect(self.db)
        self._setup()

    @staticmethod
    def _serialize_userids(userids: List[int]) -> str:
        return ",".join(map(str, sorted(userids)))

    @staticmethod
    def _deserialize_userids(userids_ser: str) -> List[int]:
        return list(map(int, userids_ser.split(",")))

    def _setup(self) -> None:
        with closing(self.con.cursor()) as cur:
            cur.execute(
                "CREATE TABLE IF NOT EXISTS pairings (guildid INTEGER, userids TEXT, channelid INTEGER, "
                "threadid INTEGER, UNIQUE (guildid, userids, channelid, threadid))"
            )
            self.con.commit()

    def insert(
        self, guild_id: int, userids: List[int], channelid: int, threadid: int
    ) -> None:
        with closing(self.con.cursor()) as cur:
            cur.execute(
                "INSERT INTO pairings VALUES (?, ?, ?, ?)",
                (guild_id, PairingsDB._serialize_userids(userids), channelid, threadid),
            )
            self.con.commit()

    def delete(
        self, guild_id: int, userids: List[int], channelid: int, threadid: int
    ) -> None:
        with closing(self.con.cursor()) as cur:
            cur.execute(
                "DELETE from pairings WHERE guildid=? and userids=? and channelid=? and threadid=?",
                (guild_id, PairingsDB._serialize_userids(userids), channelid, threadid),
            )
            self.con.commit()

    def query_userids(
        self, guild_id: int, userids: List[int], channelid: int
    ) -> Optional[int]:
        with closing(self.con.cursor()) as cur:
            res = cur.execute(
                "SELECT threadid FROM pairings WHERE guildid=? and userids=? and channelid=?",
                (guild_id, PairingsDB._serialize_userids(userids), channelid),
            )
            results = res.fetchall()
            if len(results) == 1:
                return results[0][0]


class LeetCodeDB:
    def __init__(self, path: str) -> None:
        self.db = path
        self.con = sqlite3.connect(self.db)
        self._setup()

    def _setup(self) -> None:
        with closing(self.con.cursor()) as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS leetcode (guildid INTEGER, userid INTEGER, timeblock INTEGER, 
                difficulty TEXT, UNIQUE (guildid, userid, timeblock, difficulty))
                """
            )
            self.con.commit()

    def insert(
        self, guild_id: int, user_id: int, timeblock: Timeblock, difficulty: str
    ) -> None:
        with closing(self.con.cursor()) as cur:
            cur.execute(
                "INSERT INTO leetcode (guildid, userid, timeblock, difficulty) VALUES (?, ?, ?, ?)",
                (guild_id, user_id, timeblock.value, difficulty),
            )
            self.con.commit()

    def delete(self, guild_id: int, user_id: int, timeblock: Timeblock) -> None:
        with closing(self.con.cursor()) as cur:
            cur.execute(
                "DELETE FROM leetcode WHERE guildid=? AND userid=? AND timeblock=?",
                (guild_id, user_id, timeblock.value),
            )
            self.con.commit()

    def unsubscribe(self, guild_id: int, user_id: int) -> None:
        with closing(self.con.cursor()) as cur:
            cur.execute(
                "DELETE FROM leetcode WHERE guildid=? AND userid=?", (guild_id, user_id)
            )
            self.con.commit()

    def query_timeblock_difficulty(
        self, guild_id: int, timeblock: Timeblock, difficulty: str
    ) -> List[int]:
        with closing(self.con.cursor()) as cur:
            res = cur.execute(
                "SELECT userid FROM leetcode WHERE guildid=? AND timeblock=? AND difficulty=?",
                (guild_id, timeblock.value, difficulty),
            )
            return [row[0] for row in res.fetchall()]

    def query_userid(self, guild_id: int, user_id: int) -> List[tuple]:
        with closing(self.con.cursor()) as cur:
            res = cur.execute(
                "SELECT timeblock, difficulty FROM leetcode WHERE guildid=? AND userid=?",
                (guild_id, user_id),
            )
            return res.fetchall()
