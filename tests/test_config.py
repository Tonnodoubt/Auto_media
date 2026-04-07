import unittest
from unittest.mock import patch

from app.core.config import (
    DEFAULT_LLM_SLOW_LOG_THRESHOLD_MS,
    MAX_QUALITY_FEEDBACK_MAX_RETRIES,
    MAX_OUTLINE_GENERATION_CONCURRENCY,
    MAX_SCRIPT_GENERATION_CONCURRENCY,
    Settings,
)


class SettingsValidationTests(unittest.TestCase):
    def test_negative_llm_slow_log_threshold_falls_back_to_default_with_warning(self):
        with patch("app.core.config.logger.warning") as warning_mock:
            settings = Settings(_env_file=None, llm_slow_log_threshold_ms=-1)

        self.assertEqual(settings.llm_slow_log_threshold_ms, DEFAULT_LLM_SLOW_LOG_THRESHOLD_MS)
        warning_mock.assert_called_once()
        self.assertIn("falling back to default", warning_mock.call_args.args[0])

    def test_zero_llm_slow_log_threshold_is_allowed(self):
        settings = Settings(_env_file=None, llm_slow_log_threshold_ms=0)
        self.assertEqual(settings.llm_slow_log_threshold_ms, 0)

    def test_outline_generation_concurrency_is_clamped_to_supported_max(self):
        with patch("app.core.config.logger.warning") as warning_mock:
            settings = Settings(_env_file=None, outline_generation_concurrency=9)

        self.assertEqual(settings.outline_generation_concurrency, MAX_OUTLINE_GENERATION_CONCURRENCY)
        warning_mock.assert_called_once()
        self.assertIn("exceeds max", warning_mock.call_args.args[0])

    def test_script_generation_concurrency_is_clamped_to_supported_max(self):
        with patch("app.core.config.logger.warning") as warning_mock:
            settings = Settings(_env_file=None, script_generation_concurrency=99)

        self.assertEqual(settings.script_generation_concurrency, MAX_SCRIPT_GENERATION_CONCURRENCY)
        warning_mock.assert_called_once()
        self.assertIn("exceeds max", warning_mock.call_args.args[0])

    def test_quality_feedback_max_retries_is_clamped_to_supported_max(self):
        with patch("app.core.config.logger.warning") as warning_mock:
            settings = Settings(_env_file=None, quality_feedback_max_retries=99)

        self.assertEqual(settings.quality_feedback_max_retries, MAX_QUALITY_FEEDBACK_MAX_RETRIES)
        warning_mock.assert_called_once()
        self.assertIn("exceeds max", warning_mock.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
