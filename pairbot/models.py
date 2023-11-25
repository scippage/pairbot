"""models.py

This module contains Peewee ORM models and their respective logic.
"""
import calendar
import enum
from datetime import datetime

from sqlalchemy import (
    PrimaryKeyConstraint,
    Boolean,
    Column,
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

    active: Mapped[bool]
    """Whether Pairbot is active in the channel."""

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

    available_Monday: Mapped[bool] = mapped_column(Boolean, default=False)
    available_Tuesday: Mapped[bool] = mapped_column(Boolean, default=False)
    available_Wednesday: Mapped[bool] = mapped_column(Boolean, default=False)
    available_Thursday: Mapped[bool] = mapped_column(Boolean, default=False)
    available_Friday: Mapped[bool] = mapped_column(Boolean, default=False)
    available_Saturday: Mapped[bool] = mapped_column(Boolean, default=False)
    available_Sunday: Mapped[bool] = mapped_column(Boolean, default=False)

    __table_args__ = (
        PrimaryKeyConstraint("channel_id", "user_id"),
    )

    # hack to get Schedule[day_of_week] to work
    def __getitem__(self, day_of_week: Weekday):
        return getattr(self, f"available_{day_of_week}")

    def __setitem__(self, day_of_week: Weekday, value: bool):
        setattr(self, f"available_{day_of_week}", value)

    @property
    def days_available(self):
        return [day for day in Weekday if self[day] == True]

class ScheduleAdjustment(Base):
    """Represents an adjustment to a user's availability on a specific date."""
    __tablename__ = "schedule_adjustment"

    channel_id: Mapped[int]
    """The Discord channel ID."""

    user_id: Mapped[int]
    """The Discord user ID."""

    date: Mapped[datetime]
    """The date on which the user's availability is set."""

    available: Mapped[bool]
    """Whether the user is available on this date."""

    __table_args__ = (
        PrimaryKeyConstraint("channel_id", "user_id", "date"),
    )


class Thread(Base):
    """Represents a user's membership in a Discord thread created by Pairbot."""
    __tablename__ = "pairing"

    channel_id: Mapped[int]
    """The Discord channel ID."""

    thread_id: Mapped[int]
    """The Discord thread ID"""

    user_id: Mapped[int]
    """The Discord user ID."""

    __table_args__ = (
        PrimaryKeyConstraint("channel_id", "thread_id", "user_id"),
    )
