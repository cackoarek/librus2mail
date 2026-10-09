"""Pydantic-based configuration models and settings for Librus2mail."""

from __future__ import annotations

import collections.abc
import logging
from typing import Any

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    SecretStr,
    field_validator,
)
from pydantic_settings import (
    BaseSettings,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)

logger = logging.getLogger(__name__)

KEY_ALIASES = {
    'dry-parse': 'do_not_send_first_parse',
    'dry_parse': 'do_not_send_first_parse',
    'work-in-loop': 'work_in_loop',
    'user_delay_s': 'delay_between_users_s',
}


def _serialize_value(val: Any, expose_secrets: bool = True) -> Any:
    """Helper recursively serializing models and SecretStr to primitive types."""
    if isinstance(val, SecretStr):
        return val.get_secret_value() if expose_secrets else str(val)
    if isinstance(val, BaseModel):
        res: dict[str, Any] = {}
        for k, v in val.__dict__.items():
            if not k.startswith('_'):
                res[k] = _serialize_value(v, expose_secrets)
        return res
    if isinstance(val, dict):
        return {k: _serialize_value(v, expose_secrets) for k, v in val.items()}
    if isinstance(val, list):
        return [_serialize_value(v, expose_secrets) for v in val]
    return val


class BaseConfigModel(BaseModel, collections.abc.MutableMapping):
    """Base class for configuration models supporting dictionary-like access and key aliases."""

    model_config = ConfigDict(
        extra='allow',
        coerce_numbers_to_str=True,
        populate_by_name=True,
    )

    def __getitem__(self, item: str) -> Any:
        target = KEY_ALIASES.get(item, item)
        if hasattr(self, target):
            val = getattr(self, target)
        elif item in self.__dict__:
            val = self.__dict__[item]
        elif target in self.__dict__:
            val = self.__dict__[target]
        else:
            raise KeyError(item)

        if isinstance(val, SecretStr):
            return val.get_secret_value()
        return val

    def __setitem__(self, key: str, value: Any) -> None:
        target = KEY_ALIASES.get(key, key)
        if hasattr(self, target):
            setattr(self, target, value)
        else:
            setattr(self, key, value)

    def __delitem__(self, key: str) -> None:
        target = KEY_ALIASES.get(key, key)
        if hasattr(self, target):
            delattr(self, target)
        elif key in self.__dict__:
            del self.__dict__[key]
        else:
            raise KeyError(key)

    def __contains__(self, item: object) -> bool:
        if not isinstance(item, str):
            return False
        target = KEY_ALIASES.get(item, item)
        return (
            hasattr(self, target)
            or hasattr(self, item)
            or target in self.__dict__
            or item in self.__dict__
        )

    def __iter__(self):
        return iter(self.to_dict())

    def __len__(self) -> int:
        return len(self.to_dict())

    def get(self, item: str, default: Any = None) -> Any:
        try:
            return self[item]
        except KeyError:
            return default

    def to_dict(self, expose_secrets: bool = True) -> dict[str, Any]:
        """Zwraca słownik z wartościami konfiguracji."""
        return _serialize_value(self, expose_secrets=expose_secrets)


class NonGmailSettings(BaseConfigModel):
    """Konfiguracja niestandardowego serwera SMTP."""

    smtp_host: str = "smtp.gmail.com"
    port: int = 587


class MailConfig(BaseConfigModel):
    """Konfiguracja wysyłki wiadomości e-mail (Gmail lub serwer SMTP)."""

    login: str = ""
    use_gmail: bool = True
    password: SecretStr | str | None = None
    oauth2_file: str | None = None
    non_gmail_settings: NonGmailSettings = Field(default_factory=NonGmailSettings)

    @field_validator('password', mode='after')
    @classmethod
    def wrap_password_in_secret_str(cls, v: Any) -> SecretStr | None:
        if v is None:
            return None
        if isinstance(v, SecretStr):
            return v
        return SecretStr(str(v))

    def get_password(self) -> str | None:
        if self.password is None:
            return None
        if isinstance(self.password, SecretStr):
            return self.password.get_secret_value()
        return str(self.password)


class StudentReportConfig(BaseConfigModel):
    """Konfiguracja raportu ucznia."""

    enabled: bool = True
    email: EmailStr | None = None
    template: str = "kids"


class LibrusUserConfig(BaseConfigModel):
    """Konfiguracja pojedynczego konta ucznia/rodzica w portalu Librus Synergia."""

    librus_login_name: str | None = None
    librus_login: str = ""
    librus_password: SecretStr | str = ""
    read_messages: bool = True
    read_grades: bool = True
    read_timetable: bool = True
    read_schedule: bool = True
    schedule_retention_days: int = 30
    schedule_day_offset: int = 1
    one_summary_message: bool = True
    do_not_send_first_parse: bool = Field(
        default=True,
        validation_alias=AliasChoices('do_not_send_first_parse', 'dry_parse', 'dry-parse'),
    )
    notification_receivers: list[EmailStr] = Field(default_factory=list)
    student_report: StudentReportConfig | None = None

    @field_validator('librus_login', mode='before')
    @classmethod
    def coerce_login_to_str(cls, v: Any) -> str:
        if v is None:
            return ""
        return str(v)

    @field_validator('librus_password', mode='after')
    @classmethod
    def wrap_password_in_secret_str(cls, v: Any) -> SecretStr:
        if isinstance(v, SecretStr):
            return v
        return SecretStr(str(v) if v is not None else "")

    def get_password(self) -> str:
        if isinstance(self.librus_password, SecretStr):
            return self.librus_password.get_secret_value()
        return str(self.librus_password)


class ScheduleCollectionConfig(BaseConfigModel):
    """Harmonogram odpytywania dziennika Librus."""

    mode: str = "daily"
    time: str = "16:00"
    days: str = "workdays"
    interval_hours: int = 1


class ScheduleReportItemConfig(BaseConfigModel):
    """Pojedyncza reguła harmonogramu raportu postępów."""

    name: str = "Raport postępów"
    enabled: bool = True
    frequency: str = "weekly"
    weekday: str = "friday"
    day_of_month: int | str = 1
    time: str = "17:00"
    interval_days: int = 7


class ScheduleConfig(BaseConfigModel):
    """Konfiguracja harmonogramu zadań (collection + reports)."""

    collection: ScheduleCollectionConfig = Field(default_factory=ScheduleCollectionConfig)
    reports: list[ScheduleReportItemConfig] | ScheduleReportItemConfig | None = None


class WebConfig(BaseConfigModel):
    """Konfiguracja panelu webowego (Flask)."""

    port: int = 5000
    host: str = "127.0.0.1"
    password: SecretStr | str | None = None
    secret_key: SecretStr | str | None = None
    max_login_attempts: int = 5
    lockout_duration_s: int = 900

    @field_validator('password', 'secret_key', mode='after')
    @classmethod
    def wrap_secrets(cls, v: Any) -> SecretStr | None:
        if v is None:
            return None
        if isinstance(v, SecretStr):
            return v
        return SecretStr(str(v))

    def get_password(self) -> str | None:
        if self.password is None:
            return None
        if isinstance(self.password, SecretStr):
            return self.password.get_secret_value()
        return str(self.password)


class AppSettings(BaseSettings, collections.abc.MutableMapping):
    """Główny model ustawień aplikacji Librus2mail z obsługą YAML i zmiennych środowiskowych."""

    model_config = SettingsConfigDict(
        extra='allow',
        coerce_numbers_to_str=True,
        populate_by_name=True,
        env_prefix='LIBRUS_',
        env_nested_delimiter='__',
    )

    librus_users: list[LibrusUserConfig] = Field(default_factory=list)
    delay_between_users_s: int = Field(
        default=10,
        validation_alias=AliasChoices('delay_between_users_s', 'user_delay_s'),
    )
    login_retries: int = 2
    login_retry_delay_s: int = 5
    wait_time_s: int = 3600
    work_in_loop: bool = Field(
        default=True,
        validation_alias=AliasChoices('work_in_loop', 'work-in-loop'),
    )
    storage_dir: str = "storage"
    storage_type: str = "FILES"
    send_error_notifications: bool = True
    error_cooldown_s: int = 3600
    schedule_day_offset: int = 1
    schedule_retention_days: int = 30
    one_summary_message: bool = True
    read_schedule: bool = True
    read_timetable: bool = True
    read_messages: bool = True
    read_grades: bool = True
    do_not_send_first_parse: bool = Field(
        default=True,
        validation_alias=AliasChoices('do_not_send_first_parse', 'dry_parse', 'dry-parse'),
    )
    mail: MailConfig = Field(default_factory=MailConfig)
    schedule: ScheduleConfig = Field(default_factory=ScheduleConfig)
    web: WebConfig = Field(default_factory=WebConfig)

    def __getitem__(self, item: str) -> Any:
        target = KEY_ALIASES.get(item, item)
        if hasattr(self, target):
            val = getattr(self, target)
        elif item in self.__dict__:
            val = self.__dict__[item]
        elif target in self.__dict__:
            val = self.__dict__[target]
        else:
            raise KeyError(item)

        if isinstance(val, SecretStr):
            return val.get_secret_value()
        return val

    def __setitem__(self, key: str, value: Any) -> None:
        target = KEY_ALIASES.get(key, key)
        if hasattr(self, target):
            setattr(self, target, value)
        else:
            setattr(self, key, value)

    def __delitem__(self, key: str) -> None:
        target = KEY_ALIASES.get(key, key)
        if hasattr(self, target):
            delattr(self, target)
        elif key in self.__dict__:
            del self.__dict__[key]
        else:
            raise KeyError(key)

    def __contains__(self, item: object) -> bool:
        if not isinstance(item, str):
            return False
        target = KEY_ALIASES.get(item, item)
        return (
            hasattr(self, target)
            or hasattr(self, item)
            or target in self.__dict__
            or item in self.__dict__
        )

    def __iter__(self):
        return iter(self.to_dict())

    def __len__(self) -> int:
        return len(self.to_dict())

    def get(self, item: str, default: Any = None) -> Any:
        try:
            return self[item]
        except KeyError:
            return default

    def to_dict(self, expose_secrets: bool = True) -> dict[str, Any]:
        """Zwraca słownik ze wszystkimi ustawieniami (z opcją odsłonięcia lub ukrycia sekretów)."""
        return _serialize_value(self, expose_secrets=expose_secrets)

    @classmethod
    def from_yaml(cls, yaml_path: str) -> AppSettings:
        """Wczytuje ustawienia z pliku YAML z możliwością nadpisywania zmiennymi środowiskowymi."""
        class _DynamicYamlSettings(cls):
            @classmethod
            def settings_customise_sources(
                cls_inner,
                settings_cls,
                init_settings,
                env_settings,
                dotenv_settings,
                file_secret_settings,
            ):
                return (
                    init_settings,
                    env_settings,
                    YamlConfigSettingsSource(settings_cls, yaml_file=yaml_path),
                )

        return _DynamicYamlSettings()
