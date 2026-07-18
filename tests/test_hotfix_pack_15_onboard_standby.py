"""HOTFIX PACK 15 regression tests for onboard standby policy."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "netwatchdog_standby.py").read_text(encoding="utf-8")
SERVICE = (ROOT / "netwatchdog.service").read_text(encoding="utf-8")
INSTALL = (ROOT / "install.sh").read_text(encoding="utf-8")
CONFIG = (ROOT / "config" / "netwatchdog.yaml.example").read_text(encoding="utf-8")


def test_default_mode_is_standby_and_supported_modes_are_bounded():
    assert '_net.get("onboard_backup_mode", "standby")' in SOURCE
    assert '{"active", "standby", "disabled"}' in SOURCE
    assert "onboard_backup_mode: standby" in CONFIG


def test_healthy_usb_disconnected_onboard_never_calls_recovery():
    healthy_block = SOURCE.split('if usb.good:', 1)[1].split('nw.STATE.usb_fail += 1', 1)[0]
    assert "_cancel_recovery_for_usb()" in healthy_block
    assert "_recover_onboard_for_failover" not in healthy_block
    assert "heal_onboard" not in healthy_block


def test_six_hour_standby_has_no_periodic_heal_path():
    assert "onboard_standby_probe_interval_sec" in SOURCE
    assert "STANDBY_PROBE_INTERVAL_SEC" in SOURCE
    assert "onboard_heal_failure_duration_sec" not in SOURCE
    assert "onboard_next_heal_allowed = None" in SOURCE
    assert "onboard_heal_times.clear()" in SOURCE


def test_driver_association_failure_remains_standby_unavailable():
    assert '_transition("standby_unavailable", health)' in SOURCE
    assert 'onboard_heal_suppressed_reason = "standby_usb_primary_healthy"' in SOURCE
    assert "Association request to the driver failed" not in SOURCE


def test_usb_failure_runs_one_bounded_recovery_operation():
    assert "onboard_recovery_attempted_episode" in SOURCE
    assert "if not nw.STATE.onboard_recovery_attempted_episode:" in SOURCE
    assert "for _ in range(RECOVERY_MAX_ATTEMPTS):" in SOURCE
    assert "RECOVERY_MAX_ATTEMPTS = max(1, min(3" in SOURCE


def test_usb_recovery_cancels_pending_recovery():
    cancel = SOURCE.split("def _cancel_recovery_for_usb", 1)[1].split("def _record_standby_probe", 1)[0]
    assert "onboard_required_for_failover = False" in cancel
    assert "onboard_recovery_attempted_episode = False" in cancel
    assert "onboard_next_heal_allowed = None" in cancel
    assert "onboard_heal_times.clear()" in cancel


def test_no_hourly_heal_loop_or_legacy_dashboard_event_in_standby_wrapper():
    assert 'append_event("Onboard WiFi Heal"' not in SOURCE
    assert "BACKUP_HEAL_STARTED" not in SOURCE
    assert "BACKUP_HEAL_FAILED" not in SOURCE
    assert "ONBOARD_BACKOFF_SEC" not in SOURCE


def test_transition_events_are_deduplicated():
    transition = SOURCE.split("def _transition", 1)[1].split("def _cancel_recovery_for_usb", 1)[0]
    assert "if state == nw.STATE.onboard_state:" in transition
    for event in (
        "BACKUP_STANDBY", "BACKUP_AVAILABLE", "BACKUP_UNAVAILABLE",
        "BACKUP_RECOVERY_STARTED", "BACKUP_RECOVERY_SUCCEEDED", "BACKUP_RECOVERY_FAILED",
    ):
        assert event in SOURCE


def test_diagnostics_fields_are_exposed():
    for field in (
        "onboard_backup_mode", "onboard_state", "onboard_required_for_failover",
        "onboard_recovery_attempts", "onboard_last_recovery_result",
        "onboard_next_probe", "onboard_heal_suppressed_reason",
    ):
        assert f'"{field}"' in SOURCE


def test_installer_and_service_use_standby_entrypoint():
    assert "netwatchdog_standby.py" in INSTALL
    assert "netwatchdog_standby.py" in SERVICE


def test_preserved_components_are_not_imported_or_reconfigured():
    assert "from oled" not in SOURCE
    assert "import oled" not in SOURCE
    assert "dashboard.py" not in SOURCE
    assert "status_writer.py" not in SOURCE
    assert "i2c" not in SOURCE.lower()
    assert "8080" not in SOURCE
