"""Pydantic-based configuration models and settings for Librus2mail."""

from __future__ import annotations

import collections.abc
import logging
import os
import re
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)
from pydantic_settings import (
    BaseSettings,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)

logger = logging.getLogger(__name__)

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
    """Base class for configuration models supporting dictionary-like access."""

    model_config = ConfigDict(
        extra='allow',
        coerce_numbers_to_str=True,
        populate_by_name=True,
    )

    def __getitem__(self, item: str) -> Any:
        if hasattr(self, item):
            val = getattr(self, item)
        elif item in self.__dict__:
            val = self.__dict__[item]
        else:
            raise KeyError(item)

        if isinstance(val, SecretStr):
            return val.get_secret_value()
        return val

    def __setitem__(self, key: str, value: Any) -> None:
        if hasattr(self, key):
            setattr(self, key, value)
        else:
            setattr(self, key, value)

    def __delitem__(self, key: str) -> None:
        if hasattr(self, key):
            delattr(self, key)
        elif key in self.__dict__:
            del self.__dict__[key]
        else:
            raise KeyError(key)

    def __contains__(self, item: object) -> bool:
        if not isinstance(item, str):
            return False
        return (
            hasattr(self, item)
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
    schedule_day_offset: int = 1
    one_summary_message: bool = True
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
    reports: list[ScheduleReportItemConfig] | None = None


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
    delay_between_users_s: int = 10
    login_retries: int = 2
    login_retry_delay_s: int = 5
    wait_time_s: int = 3600
    work_in_loop: bool = True
    storage_dir: str = "storage"
    send_error_notifications: bool = True
    error_cooldown_s: int = 3600
    schedule_day_offset: int = 1
    one_summary_message: bool = True
    read_schedule: bool = True
    read_timetable: bool = True
    read_messages: bool = True
    read_grades: bool = True
    semester_split_date: str | None = None
    annual_grade_algorithm: str = "all_year_weighted"
    mail: MailConfig = Field(default_factory=MailConfig)
    schedule: ScheduleConfig = Field(default_factory=ScheduleConfig)
    web: WebConfig = Field(default_factory=WebConfig)

    @model_validator(mode='before')
    @classmethod
    def assemble_env_and_defaults(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        # 1. Obsługa LIBRUS_USERS (pojedynczy prefix zamiast podwójnego LIBRUS_LIBRUS_USERS)
        env_users_raw = os.getenv('LIBRUS_USERS')
        if env_users_raw and not data.get('librus_users'):
            try:
                import json
                data['librus_users'] = json.loads(env_users_raw)
            except Exception as e:
                logger.warning(f"Nie udało się sparsować LIBRUS_USERS jako JSON: {e}")

        # 2. Obsługa pojedynczego konta ucznia ze zmiennych środowiskowych
        login = os.getenv('LIBRUS_LOGIN') or os.getenv('LIBRUS_USER_LOGIN')
        password = os.getenv('LIBRUS_PASSWORD') or os.getenv('LIBRUS_USER_PASSWORD')
        if login and password and not data.get('librus_users'):
            receivers_raw = os.getenv('LIBRUS_NOTIFICATION_RECEIVERS') or os.getenv('NOTIFICATION_RECEIVERS') or ''
            receivers: list[str] = []
            if receivers_raw.strip().startswith('['):
                import json
                try:
                    receivers = json.loads(receivers_raw)
                except Exception:
                    receivers = [r.strip() for r in receivers_raw.split(',') if r.strip()]
            elif receivers_raw:
                receivers = [r.strip() for r in receivers_raw.split(',') if r.strip()]

            user_dict: dict[str, Any] = {
                'librus_login': login,
                'librus_password': password,
                'librus_login_name': (
                    os.getenv('LIBRUS_LOGIN_NAME')
                    or os.getenv('LIBRUS_USER_NAME')
                    or f"Uczeń ({login})"
                ),
                'notification_receivers': receivers,
            }

            for flag in ('read_messages', 'read_grades', 'read_timetable', 'read_schedule', 'one_summary_message'):
                env_val = os.getenv(f'LIBRUS_{flag.upper()}')
                if env_val is not None:
                    user_dict[flag] = env_val.lower() in ('true', '1', 'yes')

            # Opcjonalny raport ucznia dla pojedynczego konta
            student_report_email = os.getenv('LIBRUS_STUDENT_REPORT_EMAIL')
            student_report_enabled = os.getenv('LIBRUS_STUDENT_REPORT_ENABLED')
            student_report_template = os.getenv('LIBRUS_STUDENT_REPORT_TEMPLATE')
            if student_report_email or student_report_enabled is not None or student_report_template:
                sr_dict: dict[str, Any] = {}
                if student_report_email:
                    sr_dict['email'] = student_report_email
                if student_report_enabled is not None:
                    sr_dict['enabled'] = student_report_enabled.lower() in ('true', '1', 'yes')
                if student_report_template:
                    sr_dict['template'] = student_report_template
                user_dict['student_report'] = sr_dict

            data['librus_users'] = [user_dict]

        # 3. Płaskie aliasy dla sekcji mail (np. LIBRUS_MAIL_LOGIN, LIBRUS_MAIL_PASSWORD, LIBRUS_SMTP_HOST)
        raw_mail = data.get('mail')
        mail_data = raw_mail if isinstance(raw_mail, dict) else (raw_mail.to_dict() if hasattr(raw_mail, 'to_dict') else {})
        if not isinstance(mail_data, dict):
            mail_data = {}

        mail_login = os.getenv('LIBRUS_MAIL_LOGIN') or os.getenv('MAIL_LOGIN')
        if mail_login and not mail_data.get('login'):
            mail_data['login'] = mail_login

        mail_password = os.getenv('LIBRUS_MAIL_PASSWORD') or os.getenv('MAIL_PASSWORD')
        if mail_password and not mail_data.get('password'):
            mail_data['password'] = mail_password

        mail_use_gmail = os.getenv('LIBRUS_MAIL_USE_GMAIL') or os.getenv('USE_GMAIL')
        if mail_use_gmail is not None and 'use_gmail' not in mail_data:
            mail_data['use_gmail'] = mail_use_gmail.lower() in ('true', '1', 'yes')

        mail_oauth2 = os.getenv('LIBRUS_MAIL_OAUTH2_FILE')
        if mail_oauth2 and not mail_data.get('oauth2_file'):
            mail_data['oauth2_file'] = mail_oauth2

        smtp_host = os.getenv('LIBRUS_SMTP_HOST') or os.getenv('SMTP_HOST')
        smtp_port = os.getenv('LIBRUS_SMTP_PORT') or os.getenv('SMTP_PORT')
        if smtp_host or smtp_port:
            raw_nongmail = mail_data.get('non_gmail_settings')
            non_gmail = raw_nongmail if isinstance(raw_nongmail, dict) else (raw_nongmail.to_dict() if hasattr(raw_nongmail, 'to_dict') else {})
            if not isinstance(non_gmail, dict):
                non_gmail = {}
            if smtp_host and not non_gmail.get('smtp_host'):
                non_gmail['smtp_host'] = smtp_host
            if smtp_port and not non_gmail.get('port'):
                try:
                    non_gmail['port'] = int(smtp_port)
                except ValueError:
                    pass
            mail_data['non_gmail_settings'] = non_gmail

        if mail_data:
            data['mail'] = mail_data

        # 4. Płaskie aliasy dla sekcji web
        raw_web = data.get('web')
        web_data = raw_web if isinstance(raw_web, dict) else (raw_web.to_dict() if hasattr(raw_web, 'to_dict') else {})
        if not isinstance(web_data, dict):
            web_data = {}

        for web_var, env_names in [
            ('host', ('LIBRUS_WEB_HOST', 'WEB_HOST')),
            ('port', ('LIBRUS_WEB_PORT', 'WEB_PORT')),
            ('password', ('LIBRUS_WEB_PASSWORD', 'WEB_PASSWORD')),
            ('secret_key', ('LIBRUS_WEB_SECRET_KEY', 'SECRET_KEY')),
            ('max_login_attempts', ('LIBRUS_WEB_MAX_LOGIN_ATTEMPTS',)),
            ('lockout_duration_s', ('LIBRUS_WEB_LOCKOUT_DURATION_S',)),
        ]:
            val = None
            for ename in env_names:
                env_v = os.getenv(ename)
                if env_v is not None:
                    val = env_v
                    break
            if val is not None and not web_data.get(web_var):
                if web_var in ('port', 'max_login_attempts', 'lockout_duration_s'):
                    try:
                        web_data[web_var] = int(val)
                    except ValueError:
                        pass
                else:
                    web_data[web_var] = val

        if web_data:
            data['web'] = web_data

        # 5. Płaskie aliasy dla harmonogramu pobierania (schedule.collection)
        raw_sched = data.get('schedule')
        sched_data = raw_sched if isinstance(raw_sched, dict) else (raw_sched.to_dict() if hasattr(raw_sched, 'to_dict') else {})
        if not isinstance(sched_data, dict):
            sched_data = {}

        raw_col = sched_data.get('collection')
        col_data = raw_col if isinstance(raw_col, dict) else (raw_col.to_dict() if hasattr(raw_col, 'to_dict') else {})
        if not isinstance(col_data, dict):
            col_data = {}

        sched_mode = os.getenv('LIBRUS_SCHEDULE_MODE')
        if sched_mode and not col_data.get('mode'):
            col_data['mode'] = sched_mode
        sched_time = os.getenv('LIBRUS_SCHEDULE_TIME')
        if sched_time and not col_data.get('time'):
            col_data['time'] = sched_time
        sched_days = os.getenv('LIBRUS_SCHEDULE_DAYS')
        if sched_days and not col_data.get('days'):
            col_data['days'] = sched_days
        sched_interval = os.getenv('LIBRUS_SCHEDULE_INTERVAL_HOURS')
        if sched_interval and not col_data.get('interval_hours'):
            try:
                col_data['interval_hours'] = int(sched_interval)
            except ValueError:
                pass

        if col_data:
            sched_data['collection'] = col_data
            data['schedule'] = sched_data

        # 6. Obsługa harmonogramu raportów (LIBRUS_SCHEDULE_REPORTS)
        sched_reports_raw = os.getenv('LIBRUS_SCHEDULE_REPORTS')
        if sched_reports_raw and not sched_data.get('reports'):
            try:
                import json
                sched_data['reports'] = json.loads(sched_reports_raw)
                data['schedule'] = sched_data
            except Exception as e:
                logger.warning(f"Nie udało się sparsować LIBRUS_SCHEDULE_REPORTS jako JSON: {e}")

        # 7. Obsługa semester_split_date i annual_grade_algorithm ze zmiennych środowiskowych
        sem_split_env = os.getenv('LIBRUS_SEMESTER_SPLIT_DATE')
        if sem_split_env and not data.get('semester_split_date'):
            data['semester_split_date'] = sem_split_env.strip()

        annual_algo_env = os.getenv('LIBRUS_ANNUAL_GRADE_ALGORITHM')
        if annual_algo_env and not data.get('annual_grade_algorithm'):
            data['annual_grade_algorithm'] = annual_algo_env.strip()

        return data

    @field_validator('semester_split_date', mode='before')
    @classmethod
    def validate_semester_split_date(cls, v: Any) -> str | None:
        if v is None:
            return None
        v_str = str(v).strip()
        if not v_str:
            return None
        if re.match(r'^\d{4}-\d{2}-\d{2}$', v_str):
            return v_str
        return None

    @field_validator('annual_grade_algorithm', mode='before')
    @classmethod
    def validate_annual_grade_algorithm(cls, v: Any) -> str:
        valid_algos = {'all_year_weighted', 'semesters_average', 'progress_favored'}
        if isinstance(v, str) and v.strip() in valid_algos:
            return v.strip()
        return 'all_year_weighted'

    def __getitem__(self, item: str) -> Any:
        if hasattr(self, item):
            val = getattr(self, item)
        elif item in self.__dict__:
            val = self.__dict__[item]
        else:
            raise KeyError(item)

        if isinstance(val, SecretStr):
            return val.get_secret_value()
        return val

    def __setitem__(self, key: str, value: Any) -> None:
        if hasattr(self, key):
            setattr(self, key, value)
        else:
            setattr(self, key, value)

    def __delitem__(self, key: str) -> None:
        if hasattr(self, key):
            delattr(self, key)
        elif key in self.__dict__:
            del self.__dict__[key]
        else:
            raise KeyError(key)

    def __contains__(self, item: object) -> bool:
        if not isinstance(item, str):
            return False
        return (
            hasattr(self, item)
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
