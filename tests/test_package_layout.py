"""Test package layout, PEP 8 snake_case modules, and backward compatibility."""

import unittest


class TestPackageLayout(unittest.TestCase):
    """Verify package imports, PEP 8 aliases, and backward compatibility shims."""

    def test_package_top_level_exports(self):
        import librus2mail
        from librus2mail import (
            BaseStorage,
            FileStorage,
            GmailSender,
            Librus,
            MailSender,
            NotLogged,
            ProgressAnalyzer,
            SmtpSender,
            configure_mail_provider,
            create_storage,
            get_predicted_grade,
            logger,
            parse_grade_date,
            parse_numeric_grade,
            parse_weight,
            read_config,
            run_collector,
            run_progress_reports,
        )

        self.assertTrue(hasattr(librus2mail, "__version__"))
        self.assertIsNotNone(Librus)
        self.assertIsNotNone(MailSender)
        self.assertIsNotNone(GmailSender)
        self.assertIsNotNone(SmtpSender)
        self.assertIsNotNone(ProgressAnalyzer)
        self.assertIsNotNone(FileStorage)
        self.assertIsNotNone(BaseStorage)
        self.assertIsNotNone(create_storage)
        self.assertIsNotNone(read_config)
        self.assertIsNotNone(logger)
        self.assertIsNotNone(run_collector)
        self.assertIsNotNone(run_progress_reports)
        self.assertIsNotNone(configure_mail_provider)
        self.assertIsNotNone(NotLogged)
        self.assertIsNotNone(parse_numeric_grade)
        self.assertIsNotNone(parse_weight)
        self.assertIsNotNone(parse_grade_date)
        self.assertIsNotNone(get_predicted_grade)

    def test_mail_sender_modules_identity(self):
        import librus2mail
        from librus2mail.gmail_sender import GmailSender
        from librus2mail.mail_sender import MailSender
        from librus2mail.smtp_sender import SmtpSender

        self.assertIs(librus2mail.MailSender, MailSender)
        self.assertIs(librus2mail.GmailSender, GmailSender)
        self.assertIs(librus2mail.SmtpSender, SmtpSender)

    def test_root_shims_modules_import(self):
        import base_logger
        import config
        import librus
        import librus_collector
        import progress_analyzer
        import progress_report
        import storage

        self.assertTrue(hasattr(base_logger, "logger"))
        self.assertTrue(hasattr(config, "read_config"))
        self.assertTrue(hasattr(librus, "Librus"))
        self.assertTrue(hasattr(librus_collector, "run_collector"))
        self.assertTrue(hasattr(progress_analyzer, "ProgressAnalyzer"))
        self.assertTrue(hasattr(progress_report, "run_progress_reports"))
        self.assertTrue(hasattr(storage, "FileStorage"))

    def test_jinja_templates_accessible_via_package(self):
        from librus2mail.mail_sender import jinja_env

        templates = [
            "messages.html",
            "notifications.html",
            "grades.html",
            "summary.html",
            "error_alert.html",
            "progress_report.html",
        ]
        for tmpl in templates:
            t = jinja_env.get_template(tmpl)
            self.assertIsNotNone(t)
            self.assertEqual(t.name, tmpl)

    def test_logging_configuration_on_demand(self):
        import logging
        import os
        import tempfile

        from librus2mail.base_logger import setup_logging

        with tempfile.TemporaryDirectory() as tmpdir:
            test_log_file = os.path.join(tmpdir, "custom.log")
            pkg_logger = setup_logging(log_file=test_log_file)
            self.assertIsNotNone(pkg_logger)
            self.assertTrue(any(isinstance(h, logging.FileHandler) for h in pkg_logger.handlers))
            self.assertTrue(any(isinstance(h, logging.StreamHandler) for h in pkg_logger.handlers))

            # Test logging through child logger
            child = logging.getLogger("librus2mail.test_submodule")
            child.info("Hello from child logger")

            # Flush and close handlers
            for h in pkg_logger.handlers:
                h.flush()
                h.close()

            with open(test_log_file, encoding="utf-8") as f:
                content = f.read()
            self.assertIn("librus2mail.test_submodule", content)
            self.assertIn("Hello from child logger", content)
