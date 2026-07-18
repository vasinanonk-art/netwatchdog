import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class OledRefreshTests(unittest.TestCase):
    def read(self, path):
        return (ROOT / path).read_text(encoding="utf-8")

    def test_display_module_is_valid_python(self):
        ast.parse(self.read("oled/display.py"))
        ast.parse(self.read("oled/main.py"))

    def test_periodic_refresh_and_counters_exist(self):
        source = self.read("oled/display.py")
        self.assertIn("FULL_REFRESH_INTERVAL_SEC = 60.0", source)
        self.assertIn("def refresh_due", source)
        for name in (
            "partial_updates",
            "full_refreshes",
            "last_full_refresh",
            "recoveries",
            "page_write_failures",
        ):
            self.assertIn(name, source)
        self.assertIn("def diagnostics", source)

    def test_differential_updates_are_preserved(self):
        source = self.read("oled/display.py")
        self.assertIn("def _changed_runs", source)
        self.assertIn("old = None if full_refresh or previous is None else previous[page]", source)
        self.assertIn("self.partial_updates += 1", source)

    def test_recovery_requests_force_refresh(self):
        source = self.read("oled/display.py")
        recover = source[source.index("def _recover"):source.index("def cmd")]
        self.assertIn("self.recoveries += 1", recover)
        self.assertIn("self.request_force_refresh()", recover)

    def test_screen_saver_and_popup_exit_request_force_refresh(self):
        source = self.read("oled/main.py")
        self.assertIn("if popup_rendered:", source)
        self.assertIn("display.request_force_refresh()", source)
        blank_section = source[source.index("if was_blank:"):source.index("shift_changed = False")]
        self.assertIn("display.request_force_refresh()", blank_section)
        self.assertIn("refresh_due = display.refresh_due()", source)

    def test_failed_page_write_invalidates_cache(self):
        source = self.read("oled/display.py")
        self.assertIn("self.page_write_failures += 1", source)
        self.assertIn("self._last_pages = None", source)
        self.assertIn("return False", source)

    def test_install_keeps_oled_package_and_service(self):
        source = self.read("install.sh")
        self.assertIn("install_oled_package", source)
        self.assertIn("service/netwatchdog-oled.service", source)
        self.assertIn("systemctl enable netwatchdog-oled", source)
        self.assertIn("restart_if_changed netwatchdog-oled", source)

    def test_no_clear_restart_or_power_cycle_added_to_refresh_path(self):
        source = self.read("oled/display.py")
        show = source[source.index("def show"):source.index("def _fit")]
        self.assertNotIn("clear(", show)
        self.assertNotIn("_recover(", show)
        self.assertNotIn("power(False)", show)


if __name__ == "__main__":
    unittest.main()
