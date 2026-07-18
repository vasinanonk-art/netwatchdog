import time
import unittest
from unittest.mock import patch

import netwatchdog as nw


class BackupWifiHotfix12Tests(unittest.TestCase):
    def setUp(self):
        nw.STATE = nw.WatchState()

    def health(self, *, connected=True, gateway=1.2, score=100):
        return nw.WifiHealth(nw.CFG.onboard_if, connected, gateway, -55, 2412.0, score)

    def usb(self, good=True):
        return nw.WifiHealth(nw.CFG.usb_if, good, 1.0 if good else None, -50, 2412.0, 100 if good else 40)

    def test_backup_probe_is_cached_while_usb_primary_is_healthy(self):
        first = self.health()
        with patch.object(nw, "onboard_health", return_value=first) as probe, patch.object(nw.time, "time", side_effect=[1000.0, 1010.0, 1061.0]):
            self.assertIs(nw.observe_onboard(self.usb()), first)
            self.assertIs(nw.observe_onboard(self.usb()), first)
            nw.observe_onboard(self.usb())
        self.assertEqual(probe.call_count, 2)

    def test_gateway_only_failure_is_degraded_but_not_healed(self):
        degraded = self.health(connected=True, gateway=None, score=60)
        nw.STATE.onboard_last_health = degraded
        nw.STATE.onboard_degraded_since = 1.0
        allowed, reason = nw._onboard_heal_allowed(5000.0, required=False)
        self.assertFalse(allowed)
        self.assertEqual(reason, "not_disconnected")

    def test_disconnected_backup_requires_sustained_duration(self):
        disconnected = self.health(connected=False, gateway=None, score=0)
        nw.STATE.onboard_last_health = disconnected
        nw.STATE.onboard_degraded_since = 1000.0
        allowed, reason = nw._onboard_heal_allowed(1000.0 + nw.CFG.onboard_heal_failure_duration_sec - 1, required=False)
        self.assertFalse(allowed)
        self.assertEqual(reason, "failure_duration")
        allowed, reason = nw._onboard_heal_allowed(1000.0 + nw.CFG.onboard_heal_failure_duration_sec, required=False)
        self.assertTrue(allowed)
        self.assertEqual(reason, "sustained_disconnect")

    def test_required_failover_can_attempt_immediate_first_heal(self):
        nw.STATE.onboard_last_health = self.health(connected=False, gateway=None, score=0)
        allowed, reason = nw._onboard_heal_allowed(2000.0, required=True)
        self.assertTrue(allowed)
        self.assertEqual(reason, "required_for_failover")

    def test_failed_heals_use_15_30_60_minute_backoff(self):
        disconnected = self.health(connected=False, gateway=None, score=0)
        nw.STATE.onboard_last_health = disconnected
        nw.STATE.onboard_degraded_since = 1.0
        with patch.object(nw, "run", return_value=False), patch.object(nw, "onboard_health", return_value=disconnected), patch.object(nw.time, "sleep"), patch.object(nw.time, "time", side_effect=[10_000.0, 10_001.0, 10_001.0]):
            nw.heal_onboard(required=True)
        self.assertEqual(nw.STATE.onboard_next_heal_allowed, 10_001.0 + 900)
        self.assertEqual(nw.STATE.onboard_backoff_step, 1)

        nw.STATE.onboard_next_heal_allowed = None
        with patch.object(nw, "run", return_value=False), patch.object(nw, "onboard_health", return_value=disconnected), patch.object(nw.time, "sleep"), patch.object(nw.time, "time", side_effect=[20_000.0, 20_001.0, 20_001.0]):
            nw.heal_onboard(required=True)
        self.assertEqual(nw.STATE.onboard_next_heal_allowed, 20_001.0 + 1800)
        self.assertEqual(nw.STATE.onboard_backoff_step, 2)

        nw.STATE.onboard_next_heal_allowed = None
        with patch.object(nw, "run", return_value=False), patch.object(nw, "onboard_health", return_value=disconnected), patch.object(nw.time, "sleep"), patch.object(nw.time, "time", side_effect=[30_000.0, 30_001.0, 30_001.0]):
            nw.heal_onboard(required=True)
        self.assertEqual(nw.STATE.onboard_next_heal_allowed, 30_001.0 + 3600)

    def test_hourly_heal_limit_suppresses_additional_attempts(self):
        now = time.time()
        nw.STATE.onboard_heal_times = [now - 10, now - 20, now - 30]
        allowed, reason = nw._onboard_heal_allowed(now, required=True)
        self.assertFalse(allowed)
        self.assertEqual(reason, "hourly_limit")

    def test_suppressed_heal_does_not_reset_failure_counter(self):
        nw.STATE.onboard_fail = 9
        nw.STATE.onboard_last_health = self.health(connected=False, gateway=None, score=0)
        nw.STATE.onboard_next_heal_allowed = time.time() + 1000
        result = nw.heal_onboard(required=True)
        self.assertFalse(result.connected)
        self.assertEqual(nw.STATE.onboard_fail, 9)

    def test_diagnostics_expose_requested_fields(self):
        payload = nw.onboard_diagnostics()
        self.assertEqual(set(payload), {
            "onboard_state", "onboard_degraded_since", "onboard_last_probe",
            "onboard_last_heal", "onboard_heal_count_hour", "onboard_next_heal_allowed",
        })

    def test_no_per_cycle_onboard_fail_log_remains(self):
        source = open("netwatchdog.py", encoding="utf-8").read()
        self.assertNotIn('log.info("ONBOARD_FAIL', source)
        self.assertNotIn('log.warning("ONBOARD_FAIL', source)
        self.assertIn("BACKUP_DEGRADED", source)
        self.assertIn("BACKUP_HEAL_SUPPRESSED", source)


if __name__ == "__main__":
    unittest.main()
