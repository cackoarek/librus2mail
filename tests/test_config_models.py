"""Testy modeli konfiguracyjnych Pydantic i pydantic-settings."""

import os
import tempfile
import unittest

from pydantic import SecretStr, ValidationError

from librus2mail.config import (
    AppSettings,
    LibrusUserConfig,
    MailConfig,
    NonGmailSettings,
    ScheduleConfig,
    TimelineConfig,
    read_config,
)


class TestConfigModels(unittest.TestCase):
    """Zestaw testów sprawdzających walidację i działanie modeli konfiguracji."""

    def test_default_app_settings(self):
        settings = AppSettings()
        self.assertEqual(settings.storage_dir, "storage")
        self.assertEqual(settings.wait_time_s, 3600)
        self.assertTrue(settings.work_in_loop)
        self.assertTrue(settings.send_error_notifications)
        self.assertEqual(len(settings.librus_users), 0)
        self.assertIsInstance(settings.mail, MailConfig)
        self.assertIsInstance(settings.mail.non_gmail_settings, NonGmailSettings)
        self.assertEqual(settings.mail.non_gmail_settings.port, 587)
        self.assertIsInstance(settings.schedule, ScheduleConfig)

    def test_dictionary_access(self):
        user = LibrusUserConfig.model_validate({
            'librus_login': '123456',
            'librus_password': 'secret_password_123',
            'read_messages': False,
        })
        self.assertFalse(user.read_messages)
        self.assertFalse(user['read_messages'])
        self.assertFalse(user.get('read_messages'))
        self.assertEqual(user['librus_password'], 'secret_password_123')
        self.assertIsInstance(user.librus_password, SecretStr)
        self.assertIn('**********', repr(user.librus_password))

        # Modyfikacja przez klucz słownikowy
        user['read_messages'] = True
        self.assertTrue(user.read_messages)
        self.assertTrue(user['read_messages'])

    def test_app_settings_fields(self):
        app = AppSettings.model_validate({
            'work_in_loop': False,
            'delay_between_users_s': 25,
            'read_grades': False,
            'semester_split_date': '2027-02-01',
            'annual_grade_algorithm': 'semesters_average',
        })
        self.assertFalse(app.work_in_loop)
        self.assertFalse(app['work_in_loop'])
        self.assertEqual(app.delay_between_users_s, 25)
        self.assertEqual(app['delay_between_users_s'], 25)
        self.assertFalse(app.read_grades)
        self.assertEqual(app.semester_split_date, '2027-02-01')
        self.assertEqual(app.annual_grade_algorithm, 'semesters_average')

        # Domyślne wartości i walidacja nieprawidłowych
        default_app = AppSettings.model_validate({})
        self.assertIsNone(default_app.semester_split_date)
        self.assertEqual(default_app.annual_grade_algorithm, 'all_year_weighted')
        self.assertTrue(default_app.read_attendance)

        user_custom = LibrusUserConfig.model_validate({
            'librus_login': '123456',
            'librus_password': 'secret_password_123',
            'read_attendance': False,
        })
        self.assertFalse(user_custom.read_attendance)
        self.assertFalse(user_custom['read_attendance'])

        invalid_app = AppSettings.model_validate({
            'semester_split_date': 'nieprawidlowa-data',
            'annual_grade_algorithm': 'nieznany_algorytm',
        })
        self.assertIsNone(invalid_app.semester_split_date)
        self.assertEqual(invalid_app.annual_grade_algorithm, 'all_year_weighted')

    def test_load_from_yaml_and_env_override(self):
        with tempfile.NamedTemporaryFile('w', suffix='.yaml', delete=False) as f:
            f.write(
                "storage_dir: yaml_storage\n"
                "wait_time_s: 1800\n"
                "mail:\n"
                "  login: yaml_user@example.com\n"
                "  password: yaml_password\n"
            )
            yaml_path = f.name

        try:
            # Bez zmiennych środowiskowych
            cfg = AppSettings.from_yaml(yaml_path)
            self.assertEqual(cfg.storage_dir, "yaml_storage")
            self.assertEqual(cfg.wait_time_s, 1800)
            self.assertEqual(cfg.mail.login, "yaml_user@example.com")
            self.assertEqual(cfg.mail.get_password(), "yaml_password")

            # Ze zmiennymi środowiskowymi nadpisującymi YAML
            os.environ['LIBRUS_STORAGE_DIR'] = "env_storage"
            os.environ['LIBRUS_MAIL__LOGIN'] = "env_user@example.com"
            os.environ['LIBRUS_MAIL__PASSWORD'] = "env_secret_pass"

            cfg_env = AppSettings.from_yaml(yaml_path)
            self.assertEqual(cfg_env.storage_dir, "env_storage")
            self.assertEqual(cfg_env.wait_time_s, 1800)  # Nienaruszone z YAML
            self.assertEqual(cfg_env.mail.login, "env_user@example.com")
            self.assertEqual(cfg_env.mail.get_password(), "env_secret_pass")
        finally:
            os.remove(yaml_path)
            os.environ.pop('LIBRUS_STORAGE_DIR', None)
            os.environ.pop('LIBRUS_MAIL__LOGIN', None)
            os.environ.pop('LIBRUS_MAIL__PASSWORD', None)

    def test_secret_str_serialization_expose_and_mask(self):
        mail = MailConfig(login='test@example.com', password='SuperSecretPassword1!')
        d_exposed = mail.to_dict(expose_secrets=True)
        d_masked = mail.to_dict(expose_secrets=False)

        self.assertEqual(d_exposed['password'], 'SuperSecretPassword1!')
        self.assertEqual(d_masked['password'], '**********')

    def test_email_validation(self):
        # Poprawny adres e-mail
        user_valid = LibrusUserConfig(
            librus_login='123',
            librus_password='pwd',
            notification_receivers=['rodzic@example.com'],
        )
        self.assertEqual(user_valid.notification_receivers, ['rodzic@example.com'])

        # Niepoprawny adres e-mail powoduje ValidationError
        with self.assertRaises(ValidationError):
            LibrusUserConfig(
                librus_login='123',
                librus_password='pwd',
                notification_receivers=['to_nie_jest_email'],
            )

    def test_read_config_example_and_minimal_files(self):
        # Sprawdzenie załadowania oficjalnych plików wzorcowych projektu
        cfg_example = read_config('config-example.yaml')
        self.assertGreaterEqual(len(cfg_example.librus_users), 2)
        self.assertEqual(cfg_example.librus_users[0].librus_login, '8912345')
        self.assertTrue(cfg_example.librus_users[0].read_messages)

        cfg_minimal = read_config('config-minimal.yaml')
        self.assertEqual(len(cfg_minimal.librus_users), 1)
        self.assertEqual(cfg_minimal.librus_users[0].librus_login, '1234567')

    def test_pure_env_configuration_without_yaml(self):
        env_vars = {
            'LIBRUS_LOGIN': '9876543',
            'LIBRUS_PASSWORD': 'env_student_password',
            'LIBRUS_LOGIN_NAME': 'Tomasz Testowy',
            'LIBRUS_NOTIFICATION_RECEIVERS': 'tata@example.com, mama@example.com',
            'LIBRUS_MAIL_LOGIN': 'robot@example.com',
            'LIBRUS_MAIL_PASSWORD': 'robot_app_password',
            'LIBRUS_MAIL_USE_GMAIL': 'false',
            'LIBRUS_SMTP_HOST': 'smtp.mojadomena.pl',
            'LIBRUS_SMTP_PORT': '465',
            'LIBRUS_WEB_PASSWORD': 'super_web_pass',
            'LIBRUS_SCHEDULE_MODE': 'daily',
            'LIBRUS_SCHEDULE_TIME': '18:15',
        }
        for k, v in env_vars.items():
            os.environ[k] = v

        try:
            # Wczytanie z nieistniejącego pliku powinno pomyślnie użyć konfiguracji z ENV
            cfg = read_config('plik_ktory_na_pewno_nie_istnieje.yaml')
            self.assertEqual(len(cfg.librus_users), 1)
            u = cfg.librus_users[0]
            self.assertEqual(u.librus_login, '9876543')
            self.assertEqual(u.get_password(), 'env_student_password')
            self.assertEqual(u.librus_login_name, 'Tomasz Testowy')
            self.assertEqual(u.notification_receivers, ['tata@example.com', 'mama@example.com'])
            self.assertEqual(cfg.mail.login, 'robot@example.com')
            self.assertEqual(cfg.mail.get_password(), 'robot_app_password')
            self.assertFalse(cfg.mail.use_gmail)
            self.assertEqual(cfg.mail.non_gmail_settings.smtp_host, 'smtp.mojadomena.pl')
            self.assertEqual(cfg.mail.non_gmail_settings.port, 465)
            self.assertEqual(cfg.web.get_password(), 'super_web_pass')
            self.assertEqual(cfg.schedule.collection.mode, 'daily')
            self.assertEqual(cfg.schedule.collection.time, '18:15')
        finally:
            for k in env_vars:
                os.environ.pop(k, None)

    def test_env_librus_users_json(self):
        import json
        users_json = json.dumps([
            {
                'librus_login': '111111',
                'librus_password': 'pass1',
                'librus_login_name': 'Dziecko 1',
                'notification_receivers': ['rodzic1@example.com'],
            },
            {
                'librus_login': '222222',
                'librus_password': 'pass2',
                'librus_login_name': 'Dziecko 2',
                'notification_receivers': ['rodzic2@example.com'],
            },
        ])
        os.environ['LIBRUS_USERS'] = users_json
        try:
            cfg = AppSettings()
            self.assertEqual(len(cfg.librus_users), 2)
            self.assertEqual(cfg.librus_users[0].librus_login, '111111')
            self.assertEqual(cfg.librus_users[1].librus_login, '222222')
        finally:
            os.environ.pop('LIBRUS_USERS', None)

    def test_timeline_config_model_and_validation(self):
        """Weryfikuje model TimelineConfig, domyślne wartości oraz obcinanie dni do zakresu 1-14."""
        default_tl = TimelineConfig()
        self.assertTrue(default_tl.enabled)
        self.assertEqual(default_tl.days, 5)
        self.assertFalse(default_tl.hide_weekends)
        self.assertFalse(default_tl.reverse_order)
        self.assertEqual(len(default_tl.event_types), 5)

        # Clamping dni do zakresu 1-14
        custom_tl = TimelineConfig(days=99, hide_weekends=True, reverse_order=True)
        self.assertEqual(custom_tl.days, 14)
        self.assertTrue(custom_tl.hide_weekends)
        self.assertTrue(custom_tl.reverse_order)

        low_tl = TimelineConfig(days=-5)
        self.assertEqual(low_tl.days, 1)

    def test_timeline_serialization_and_extra_preservation(self):
        """Weryfikuje, że AppSettings.to_dict() oraz dict(app) zachowują sekcję timeline oraz dynamiczne pola extra."""
        app = AppSettings.model_validate({
            'timeline': {
                'enabled': True,
                'days': 8,
                'hide_weekends': True,
                'reverse_order': True,
                'event_types': ['grades', 'messages'],
            },
            'custom_extra_key': 'preserved_value',
        })
        self.assertEqual(app.timeline.days, 8)
        self.assertTrue(app.timeline.hide_weekends)
        self.assertTrue(app.timeline.reverse_order)

        # Serializacja to_dict
        d = app.to_dict()
        self.assertIn('timeline', d)
        self.assertEqual(d['timeline']['days'], 8)
        self.assertTrue(d['timeline']['hide_weekends'])
        self.assertTrue(d['timeline']['reverse_order'])
        self.assertIn('custom_extra_key', d)
        self.assertEqual(d['custom_extra_key'], 'preserved_value')

        # Konwersja dict(app)
        dict_app = dict(app)
        self.assertIn('timeline', dict_app)
        self.assertEqual(dict_app['timeline']['days'], 8)
        self.assertTrue(dict_app['timeline']['hide_weekends'])
        self.assertTrue(dict_app['timeline']['reverse_order'])
        self.assertIn('custom_extra_key', dict_app)


if __name__ == '__main__':
    unittest.main()
