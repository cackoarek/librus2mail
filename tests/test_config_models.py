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

    def test_key_aliases_and_dictionary_access(self):
        user = LibrusUserConfig.model_validate({
            'librus_login': '123456',
            'librus_password': 'secret_password_123',
            'dry-parse': False,
        })
        self.assertFalse(user.do_not_send_first_parse)
        self.assertFalse(user['dry-parse'])
        self.assertFalse(user['dry_parse'])
        self.assertFalse(user.get('dry-parse'))
        self.assertEqual(user['librus_password'], 'secret_password_123')
        self.assertIsInstance(user.librus_password, SecretStr)
        self.assertIn('**********', repr(user.librus_password))

        # Modyfikacja przez klucz aliasu
        user['dry-parse'] = True
        self.assertTrue(user.do_not_send_first_parse)
        self.assertTrue(user['dry-parse'])

    def test_app_settings_key_aliases(self):
        app = AppSettings.model_validate({
            'work-in-loop': False,
            'user_delay_s': 25,
            'dry-parse': False,
        })
        self.assertFalse(app.work_in_loop)
        self.assertFalse(app['work-in-loop'])
        self.assertFalse(app['work_in_loop'])
        self.assertEqual(app.delay_between_users_s, 25)
        self.assertEqual(app['user_delay_s'], 25)
        self.assertEqual(app['delay_between_users_s'], 25)
        self.assertFalse(app.do_not_send_first_parse)

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


if __name__ == '__main__':
    unittest.main()
