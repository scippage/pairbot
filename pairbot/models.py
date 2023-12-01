"""models.py

This module contains Peewee ORM models and their respective logic.
"""
import calendar
import enum
from datetime import datetime

from typing import (
    Optional,
    Union,
)

from sqlalchemy import (
    PrimaryKeyConstraint,
    Boolean,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
)


class Base(DeclarativeBase):
    pass


class PairingChannel(Base):
    """A Discord channel in which Pairbot has been allowed to operate."""
    __tablename__ = "channel"

    guild_id: Mapped[int]
    """The Discord guild ID."""

    channel_id: Mapped[int]
    """The Discord channel ID."""

    leetcode_integration: Mapped[bool]
    """Whether leetcode integration is active in the channel or not."""

    __table_args__ = (
        PrimaryKeyConstraint("guild_id", "channel_id",),
    )


class Weekday(enum.IntEnum):
    """An enum representing the day of the week (0-6 starting from Monday)."""
    Monday = 0
    Tuesday = 1
    Wednesday = 2
    Thursday = 3
    Friday = 4
    Saturday = 5
    Sunday = 6

    def __str__(self):
        return calendar.day_name[self]


class Schedule(Base):
    """Represents the availability of a user in a channel on a given day of the week"""
    __tablename__ = "schedule"

    channel_id: Mapped[int]
    """The Discord channel ID."""

    user_id: Mapped[int]
    """The Discord user ID."""

    available_0: Mapped[bool] = mapped_column(Boolean, default=False)
    available_1: Mapped[bool] = mapped_column(Boolean, default=False)
    available_2: Mapped[bool] = mapped_column(Boolean, default=False)
    available_3: Mapped[bool] = mapped_column(Boolean, default=False)
    available_4: Mapped[bool] = mapped_column(Boolean, default=False)
    available_5: Mapped[bool] = mapped_column(Boolean, default=False)
    available_6: Mapped[bool] = mapped_column(Boolean, default=False)

    __table_args__ = (
        PrimaryKeyConstraint("channel_id", "user_id"),
    )

    # Utility methods

    def is_available_on(self, day_of_week: Weekday) -> bool:
        return getattr(self, f"available_{int(day_of_week)}")

    def set_availability_on(self, day_of_week: Weekday, value: bool):
        setattr(self, f"available_{int(day_of_week)}", value)

    def set_availability_every_day(self, value: bool):
        for day in Weekday:
            self.set_availability_on(day, value)

    def days_available(self) -> list[Weekday]:
        return [day for day in Weekday if self.is_available_on(day)]

    def days_unavailable(self) -> list[Weekday]:
        return [day for day in Weekday if not self.is_available_on(day)]

    def num_days_available(self) -> int:
        return sum(1 for day in Weekday if self.is_available_on(day))


class Skip(Base):
    """Represents an adjustment to a user's availability on a specific date."""
    __tablename__ = "skip"

    channel_id: Mapped[int]
    """The Discord channel ID."""

    user_id: Mapped[int]
    """The Discord user ID."""

    date: Mapped[datetime]
    """The date on which the user's availability is set."""

    __table_args__ = (
        PrimaryKeyConstraint("channel_id", "user_id", "date"),
    )


class Pairing(Base):
    """Represents a Discord thread created by Pairbot."""
    __tablename__ = "pairing"

    channel_id: Mapped[int]
    """The Discord channel ID."""

    thread_id: Mapped[int]
    """The Discord thread ID"""

    user_1_id: Mapped[int]
    """The first Discord user ID."""

    user_2_id: Mapped[int]
    """The second Discord user ID."""

    user_3_id: Mapped[Optional[int]]
    """The third Discord user ID."""

    __table_args__ = (
        PrimaryKeyConstraint("channel_id", "thread_id"),
    )
