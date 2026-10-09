"""Domenowe modele danych Librus2mail (oceny, wiadomości, ogłoszenia, terminarz, plan lekcji)."""

from __future__ import annotations

import collections.abc
from typing import Any

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
)


class BaseDomainModel(BaseModel, collections.abc.MutableMapping):
    """Bazowa klasa dla obiektów domenowych ze wsparciem dla dostępu słownikowego."""

    model_config = ConfigDict(
        extra='allow',
        coerce_numbers_to_str=True,
        populate_by_name=True,
    )

    def __getitem__(self, item: str) -> Any:
        if hasattr(self, item):
            val = getattr(self, item)
            return val
        extra = getattr(self, '__pydantic_extra__', None)
        if extra and item in extra:
            return extra[item]
        raise KeyError(item)

    def __setitem__(self, key: str, value: Any) -> None:
        setattr(self, key, value)

    def __delitem__(self, key: str) -> None:
        if hasattr(self, key):
            delattr(self, key)
        else:
            extra = getattr(self, '__pydantic_extra__', None)
            if extra and key in extra:
                del extra[key]
            else:
                raise KeyError(key)

    def __contains__(self, item: object) -> bool:
        if not isinstance(item, str):
            return False
        extra = getattr(self, '__pydantic_extra__', None)
        return hasattr(self, item) or (extra is not None and item in extra)

    def __iter__(self):
        return iter(self.to_dict())

    def __len__(self) -> int:
        return len(self.to_dict())

    def get(self, item: str, default: Any = None) -> Any:
        try:
            return self[item]
        except KeyError:
            return default

    def to_dict(self) -> dict[str, Any]:
        """Zwraca surowy słownik zgodny z JSON / PyYAML."""
        return self.model_dump()


class Grade(BaseDomainModel):
    """Model pojedynczej oceny szkolnej z dziennika Librus."""

    id: str
    subject: str
    grade: str
    category: str = "-"
    date: str = "-"
    teacher: str = "-"
    weight: str = "-"
    comment: str = "-"
    href: str = ""
    added_at: str | None = None

    @property
    def numeric_value(self) -> float | None:
        """Parsuje wartość oceny na liczbę zmiennoprzecinkową (np. '5+' -> 5.25)."""
        from librus2mail.progress_analyzer import parse_numeric_grade
        return parse_numeric_grade(self.grade)

    @property
    def weight_value(self) -> float:
        """Zwraca wagę oceny jako float (domyślnie 1.0)."""
        from librus2mail.progress_analyzer import parse_weight
        return parse_weight(self.weight)


class Message(BaseDomainModel):
    """Model pojedynczej wiadomości prywatnej z dziennika Librus."""

    id: str
    title: str
    sender: str
    datetime: str = Field(validation_alias=AliasChoices('datetime', 'date'))
    is_unread: bool = False
    link: str = ""
    has_attachment: bool = False
    body: str | None = None
    added_at: str | None = None

    @property
    def date(self) -> str:
        return self.datetime

    def __getitem__(self, item: str) -> Any:
        if item == 'date' and 'date' not in (getattr(self, '__pydantic_extra__', None) or {}):
            return self.datetime
        return super().__getitem__(item)


class Announcement(BaseDomainModel):
    """Model ogłoszenia szkolnego ze strony głównej Librus Synergia."""

    id: str
    title: str
    sender: str = Field(validation_alias=AliasChoices('sender', 'author'))
    datetime: str = Field(validation_alias=AliasChoices('datetime', 'date'))
    is_unread: bool = False
    body: str = ""
    added_at: str | None = None

    @property
    def author(self) -> str:
        return self.sender

    @property
    def date(self) -> str:
        return self.datetime

    def __getitem__(self, item: str) -> Any:
        if item == 'author' and 'author' not in (getattr(self, '__pydantic_extra__', None) or {}):
            return self.sender
        if item == 'date' and 'date' not in (getattr(self, '__pydantic_extra__', None) or {}):
            return self.datetime
        return super().__getitem__(item)


# Alias dla kompatybilności wstecznej
Notification = Announcement


class TimetableEntry(BaseDomainModel):
    """Model wpisu w terminarzu szkolnym (sprawdzian, kartkówka, praca domowa, nieobecność)."""

    id: str
    date: str
    type: str = "event"
    category: str = "Inne"
    subject: str = ""
    lesson_no: str | int = ""
    teacher: str = ""
    description: str = ""
    add_date: str = ""
    time: str = ""
    raw_text: str = ""


class ScheduleLesson(BaseDomainModel):
    """Model pojedynczej godziny lekcyjnej w planie lekcji."""

    id: str
    date: str
    lesson_no: int = 0
    time_from: str = ""
    time_to: str = ""
    time_range: str = ""
    subject: str = ""
    teacher: str = ""
    classroom: str = ""
    is_cancelled: bool = False
    is_substitution: bool = False
    is_moved: bool = False
    substitution_info: str = ""
    info: str = ""
    raw_text: str = ""


# Alias dla kompatybilności wstecznej
ScheduleEntry = ScheduleLesson


__all__ = [
    "Announcement",
    "BaseDomainModel",
    "Grade",
    "Message",
    "Notification",
    "ScheduleEntry",
    "ScheduleLesson",
    "TimetableEntry",
]
