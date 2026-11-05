from datetime import datetime, timezone
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
import runpy
from unittest.mock import patch

from pipeline.common import ROOT, StudioError, atomic_json, load_json, resource_lock, utc_now
from pipeline import hero_stop


class HeroStopTests(unittest.TestCase):
    def setUp(self):
        scratch = ROOT / ".studio/hero-stop-tests"
        scratch.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.executable = self.root / "engine/UnrealEditor"
        self.project = self.root / ".studio/lyra/projects/LyraStarterGame/Lyra.uproject"
        self.game_map = "/NovanodeHeroes/Maps/L_HeroSandbox_v2"
        self.job = "play-v2-123456abcdef"
        self.path = self.root / ".studio/evidence" / f"hero-sandbox-job-{self.job}.json"
        ticks = Path(f"/proc/{os.getpid()}/stat").read_text().rsplit(")", 1)[1].split()[19]
        boot = int(next(line.split()[1] for line in Path("/proc/stat").read_text().splitlines() if line.startswith("btime ")))
        self.row = {"job_id": self.job, "operation": "play-v2", "state": "running_unknown", "pid": 246810,
                    "process_start_ticks": ticks,
                    "started_at": datetime.fromtimestamp(boot + int(ticks) / os.sysconf("SC_CLK_TCK"), timezone.utc).isoformat(),
                    "command": [str(self.executable), str(self.project), self.game_map, "-game", "-DisablePython"],
                    "human_approval": "pending"}
        self.write_job()
        self.current = {"ticks": ticks, "parent_pid": 12345, "lifecycle": "S", "uid": os.getuid(),
                        "argv": self.row["command"], "executable": str(self.executable),
                        "caught": 1 << (signal.SIGINT - 1), "ignored": 0}
        self.parent = {"ticks": str(int(ticks) - 1), "lifecycle": "S", "uid": os.getuid(),
                       "argv": [sys.executable, str(self.root / "projects/hero-sandbox/manage.py"), "play-v2"]}
        owner = self

        class FakeProcess:
            def __init__(self):
                self.dead = False
                self.signals = 0
                self.closed = False
                self.terminal_state = "completed"
                self.exit_code = 0

            def exited(self, timeout=0):
                return self.dead

            def request_exit(self):
                self.signals += 1
                if self.terminal_state is not None:
                    self.dead = True
                    row = load_json(owner.path)
                    row.update(state=self.terminal_state, exit_code=self.exit_code, finished_at=utc_now(),
                               summary={"normal_exit_marker": self.exit_code == 0})
                    atomic_json(owner.path, row)  # Simulated owning launcher, not the stop client.

            def close(self):
                self.closed = True

        self.process = FakeProcess()
        self.proc_patch = patch("pipeline.hero_stop._proc", side_effect=lambda pid, **kwargs:
                                dict(self.current) if pid == self.row["pid"] else dict(self.parent))
        self.fd_patch = patch("pipeline.hero_stop.PidfdProcess", return_value=self.process)
        self.proc_patch.start()
        self.fd_mock = self.fd_patch.start()
        self.addCleanup(self.proc_patch.stop)
        self.addCleanup(self.fd_patch.stop)

    def write_job(self):
        atomic_json(self.path, self.row)

    def stop(self, **kwargs):
        return hero_stop.stop_session(self.root, self.executable, self.project, self.game_map, **kwargs)

    def test_stops_only_the_bound_game_and_waits_for_launcher_exit(self):
        with resource_lock("integrator", self.root), resource_lock("unreal-editor", self.root):
            result = self.stop()
        self.assertEqual(self.process.signals, 1)
        self.assertTrue(self.process.closed)
        self.assertEqual(result["state"], "stopped")
        self.assertTrue(result["launcher_recorded_exit"])
        self.assertFalse(result["native_success_verified"])
        self.assertEqual(load_json(self.path)["human_approval"], "pending")
        receipt = load_json(self.root / result["receipt"])
        self.assertEqual(receipt["state"], "stopped")

    def test_nonzero_native_exit_is_reported_not_invented_success(self):
        self.process.terminal_state = "blocked"
        self.process.exit_code = 6
        result = self.stop()
        self.assertEqual(result["native_exit_code"], 6)
        self.assertEqual(result["native_job_state"], "blocked")
        self.assertFalse(result["normal_exit_marker"])
        self.assertFalse(result["native_success_verified"])

    def test_request_identity_is_persisted_before_signal_delivery(self):
        request = self.process.request_exit
        def check_receipt():
            receipt = load_json(next(self.path.parent.glob("hero-sandbox-stop-*.json")))
            self.assertEqual(receipt["state"], "requesting_unknown")
            self.assertIsNone(receipt["signal_sent"])
            self.assertEqual(receipt["job_id"], self.job)
            request()
        self.process.request_exit = check_receipt
        self.assertEqual(self.stop()["state"], "stopped")

    def test_process_ending_before_delivery_does_not_signal_a_new_pid(self):
        def gone():
            self.process.dead = True
            row = load_json(self.path)
            row.update(state="completed", exit_code=0, finished_at=utc_now())
            atomic_json(self.path, row)
            raise ProcessLookupError
        self.process.request_exit = gone
        result = self.stop()
        self.assertEqual(result["state"], "stopped")
        self.assertFalse(result["signal_sent"])
        self.assertEqual(self.process.signals, 0)

    def test_dry_run_has_no_signal_receipt_or_lock_write(self):
        before = {p.relative_to(self.root).as_posix(): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        result = self.stop(dry_run=True)
        self.assertEqual(result["state"], "dry_run")
        self.assertEqual(self.process.signals, 0)
        self.fd_mock.assert_not_called()
        self.assertFalse((self.root / ".studio/locks").exists())
        self.assertEqual(before, {p.relative_to(self.root).as_posix(): p.read_bytes()
                                  for p in self.root.rglob("*") if p.is_file()})

    def test_no_pending_session_is_a_write_free_noop(self):
        self.row["state"] = "blocked"
        self.write_job()
        result = self.stop()
        self.assertEqual(result["state"], "not_running")
        self.fd_mock.assert_not_called()
        self.assertFalse((self.root / ".studio/locks").exists())

    def test_absent_studio_is_a_noop(self):
        with tempfile.TemporaryDirectory(dir=self.root) as clean:
            result = hero_stop.stop_session(Path(clean), self.executable, self.project, self.game_map)
            self.assertEqual(result["state"], "not_running")
            self.assertEqual(list(Path(clean).iterdir()), [])

    def test_ambiguous_jobs_require_explicit_selection(self):
        another = {**self.row, "job_id": "play-v2-aaaaaaaaaaaa"}
        atomic_json(self.path.parent / "hero-sandbox-job-play-v2-aaaaaaaaaaaa.json", another)
        with self.assertRaisesRegex(StudioError, "Ambiguous"):
            self.stop()
        self.assertEqual(self.process.signals, 0)
        self.assertEqual(self.stop(job_id=self.job)["state"], "stopped")

    def test_editor_build_and_traversal_targets_are_refused(self):
        for job in ("editor-v2-aaaaaaaaaaaa", "build-aaaaaaaaaaaa", "../escape", "play-v2-bad"):
            with self.subTest(job=job), self.assertRaises(StudioError):
                self.stop(job_id=job)
        self.assertEqual(self.process.signals, 0)

    def test_wrong_pid_uid_executable_ticks_or_argv_never_signal(self):
        cases = {"uid": os.getuid() + 1, "ticks": "0", "executable": "/other/UnrealEditor",
                 "argv": ["other-project"], "lifecycle": "Z"}
        original = dict(self.current)
        for key, value in cases.items():
            with self.subTest(field=key):
                self.current = {**original, key: value}
                with self.assertRaises(StudioError):
                    self.stop()
                self.assertEqual(self.process.signals, 0)
        self.current = original

    def test_wrong_project_map_or_non_game_command_is_refused(self):
        for command in ([str(self.executable), "/other/Lyra.uproject", self.game_map, "-game"],
                        [str(self.executable), str(self.project), "/Game/Other", "-game"],
                        [str(self.executable), str(self.project), self.game_map]):
            with self.subTest(command=command):
                self.row["command"] = command
                self.current["argv"] = command
                self.write_job()
                with self.assertRaises(StudioError):
                    self.stop()
        self.assertEqual(self.process.signals, 0)

    def test_boot_or_parent_identity_mismatch_is_refused(self):
        original_date = self.row["started_at"]
        self.row["started_at"] = "2000-01-01T00:00:00+00:00"
        self.write_job()
        with self.assertRaisesRegex(StudioError, "boot identity"):
            self.stop()
        self.row["started_at"] = original_date
        self.write_job()
        self.parent["argv"] = ["unrelated-service"]
        with self.assertRaisesRegex(StudioError, "launcher identity"):
            self.stop()
        self.assertEqual(self.process.signals, 0)

    def test_absent_process_or_launcher_does_not_clear_hold(self):
        original = self.path.read_bytes()
        with patch("pipeline.hero_stop._proc", side_effect=FileNotFoundError):
            with self.assertRaisesRegex(StudioError, "outcome unknown"):
                self.stop()
        self.assertEqual(original, self.path.read_bytes())
        self.assertEqual(self.process.signals, 0)

    def test_missing_or_ignored_handler_does_not_signal(self):
        for caught, ignored in ((0, 0), (self.current["caught"], self.current["caught"])):
            with self.subTest(caught=caught, ignored=ignored):
                self.current.update(caught=caught, ignored=ignored)
                with self.assertRaisesRegex(StudioError, "SIGINT handler"):
                    self.stop()
        self.assertEqual(self.process.signals, 0)

    def test_reserved_identity_is_not_a_stoppable_process(self):
        self.row.pop("pid")
        self.row["state"] = "reserved"
        self.write_job()
        with self.assertRaisesRegex(StudioError, "recorded native PID"):
            self.stop()
        self.assertEqual(self.process.signals, 0)

    def test_pidfd_unsupported_fails_closed(self):
        with patch("pipeline.hero_stop.PidfdProcess", side_effect=StudioError("Linux pidfd unavailable")):
            with self.assertRaisesRegex(StudioError, "pidfd"):
                self.stop()
        self.assertEqual(self.process.signals, 0)

    def test_process_timeout_never_escalates_or_resubmits(self):
        self.process.terminal_state = None
        original = self.path.read_bytes()
        result = self.stop(timeout=1)
        self.assertEqual(result["state"], "outcome_unknown")
        self.assertEqual(result["reason"], "process_exit_timeout")
        self.assertEqual(self.process.signals, 1)
        self.assertEqual(original, self.path.read_bytes())
        with self.assertRaisesRegex(StudioError, "Earlier stop unresolved"):
            self.stop()
        self.assertEqual(self.process.signals, 1)

    def test_exit_without_launcher_journal_remains_unknown(self):
        def exit_only():
            self.process.signals += 1
            self.process.dead = True
        self.process.request_exit = exit_only
        original = self.path.read_bytes()
        result = self.stop(timeout=1)
        self.assertEqual(result["reason"], "launcher_journal_timeout")
        self.assertTrue(result["reconciliation_required"])
        self.assertEqual(original, self.path.read_bytes())

    def test_interruption_leaves_durable_unknown_receipt_and_closes_fd(self):
        with patch("pipeline.hero_stop._wait", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.stop()
        receipt = load_json(next(self.path.parent.glob("hero-sandbox-stop-*.json")))
        self.assertEqual(receipt["state"], "outcome_unknown")
        self.assertTrue(receipt["reconciliation_required"])
        self.assertTrue(self.process.closed)
        self.assertEqual(self.process.signals, 1)

    def test_exit_during_validation_never_signals_a_replacement(self):
        self.process.dead = True
        original = self.path.read_bytes()
        with self.assertRaisesRegex(StudioError, "exited during"):
            self.stop()
        self.assertTrue(self.process.closed)
        self.assertEqual(self.process.signals, 0)
        self.assertEqual(self.path.read_bytes(), original)

    def test_interruption_during_signal_delivery_keeps_delivery_unknown(self):
        def uncertain_delivery():
            self.process.signals += 1
            raise KeyboardInterrupt
        self.process.request_exit = uncertain_delivery
        with self.assertRaises(KeyboardInterrupt):
            self.stop()
        receipt = load_json(next(self.path.parent.glob("hero-sandbox-stop-*.json")))
        self.assertEqual(receipt["state"], "outcome_unknown")
        self.assertIsNone(receipt["signal_sent"])
        with self.assertRaisesRegex(StudioError, "Earlier stop unresolved"):
            self.stop()
        self.assertEqual(self.process.signals, 1)

    def test_journal_identity_change_after_request_is_not_a_success(self):
        request = self.process.request_exit
        def changed_identity():
            request()
            row = load_json(self.path)
            row["process_start_ticks"] = "different"
            atomic_json(self.path, row)
        self.process.request_exit = changed_identity
        with self.assertRaisesRegex(StudioError, "journal identity changed"):
            self.stop()
        receipt = load_json(next(self.path.parent.glob("hero-sandbox-stop-*.json")))
        self.assertEqual(receipt["state"], "outcome_unknown")
        self.assertEqual(self.process.signals, 1)

    def test_late_launcher_journal_is_observed_without_a_second_signal(self):
        request = self.process.request_exit
        original = dict(self.row)
        final = {}
        def delayed_request():
            request()
            final.update(load_json(self.path))
            atomic_json(self.path, original)
        real_read = hero_stop._read
        after_exit_reads = 0
        def delayed_read(root, path):
            nonlocal after_exit_reads
            if path == self.path and self.process.dead:
                after_exit_reads += 1
                if after_exit_reads == 2:
                    atomic_json(self.path, final)
            return real_read(root, path)
        self.process.request_exit = delayed_request
        with patch("pipeline.hero_stop._read", side_effect=delayed_read):
            result = self.stop()
        self.assertEqual(result["state"], "stopped")
        self.assertGreaterEqual(after_exit_reads, 2)
        self.assertEqual(self.process.signals, 1)

    def test_malformed_symlink_oversized_and_inventory_limits_fail_closed(self):
        original = self.path.read_bytes()
        self.path.write_text("{broken")
        with self.assertRaises(StudioError):
            self.stop()
        self.path.write_bytes(original)
        with patch.object(hero_stop, "MAX_BYTES", 10), self.assertRaises(StudioError):
            self.stop()
        target = self.root / "owned-target.json"
        target.write_bytes(original)
        self.path.unlink()
        self.path.symlink_to(target)
        with self.assertRaises(StudioError):
            self.stop()
        self.path.unlink()
        self.path.write_bytes(original)
        with patch.object(hero_stop, "MAX_RECORDS", 0), self.assertRaises(StudioError):
            self.stop()
        self.assertEqual(self.process.signals, 0)

    def test_timeout_bounds_and_busy_stop_lock_refuse_without_signals(self):
        for timeout in (0, 61, True, "20"):
            with self.subTest(timeout=timeout), self.assertRaises(StudioError):
                self.stop(timeout=timeout)
        with resource_lock("hero-play-stop", self.root), self.assertRaisesRegex(StudioError, "Resource busy"):
            self.stop()
        self.assertEqual(self.process.signals, 0)


class HeroStopManagerTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location("hero_stop_manager", ROOT / "projects/hero-sandbox/manage.py")
        self.manager = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.manager)

    def test_stop_route_never_imports_native_startup_helpers(self):
        with (patch("pipeline.hero_stop.stop_session", return_value={"state": "dry_run"}) as stop,
              patch.dict(sys.modules, {"lyra_startup": None}), patch("builtins.print")):
            self.assertEqual(self.manager.run("stop", dry_run=True), 0)
        self.assertTrue(stop.call_args.kwargs["dry_run"])

    def test_stop_unknown_outcome_returns_nonzero(self):
        with patch("pipeline.hero_stop.stop_session", return_value={"state": "outcome_unknown"}), patch("builtins.print"):
            self.assertEqual(self.manager.run("stop"), 1)

    def test_stop_cli_forwards_options_without_native_helper(self):
        path = ROOT / "projects/hero-sandbox/manage.py"
        argv = [str(path), "stop", "--job-id", "play-v2-123456abcdef", "--timeout", "3", "--dry-run"]
        with (patch.object(sys, "argv", argv), patch.dict(sys.modules, {"lyra_startup": None}),
              patch("pipeline.hero_stop.stop_session", return_value={"state": "dry_run"}) as stop,
              contextlib.redirect_stdout(io.StringIO())):
            with self.assertRaises(SystemExit) as exit:
                runpy.run_path(str(path), run_name="__main__")
        self.assertEqual(exit.exception.code, 0)
        self.assertEqual(stop.call_args.kwargs, {"job_id": "play-v2-123456abcdef", "timeout": 3, "dry_run": True})

    def test_stop_options_cannot_change_existing_launch_behavior(self):
        path = ROOT / "projects/hero-sandbox/manage.py"
        with (patch.object(sys, "argv", [str(path), "play-v2", "--dry-run"]),
              patch.dict(sys.modules, {"lyra_startup": None}), contextlib.redirect_stderr(io.StringIO())):
            with self.assertRaises(SystemExit) as exit:
                runpy.run_path(str(path), run_name="__main__")
        self.assertEqual(exit.exception.code, 2)

    def test_real_exit_is_persisted_before_failed_postcheck(self):
        scratch = ROOT / ".studio/hero-stop-tests"
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as temporary:
            path = Path(temporary) / "journal.json"
            state = {"state": "running_unknown", "human_approval": "pending"}
            with patch.object(self.manager, "baseline", side_effect=StudioError("owned postcheck failure")):
                with self.assertRaises(StudioError):
                    self.manager.record_exit(state, path, 0, Path(temporary) / "not-read.log")
            saved = load_json(path)
            self.assertEqual(saved["state"], "blocked")
            self.assertEqual(saved["exit_code"], 0)
            self.assertTrue(saved["process_exit_observed"])
            self.assertEqual(saved["post_exit_verification"], "failed_or_interrupted")
            self.assertEqual(saved["human_approval"], "pending")


@unittest.skipUnless(hasattr(os, "pidfd_open") and hasattr(signal, "pidfd_send_signal"), "Linux pidfd required")
class HeroStopProcessTests(unittest.TestCase):
    def test_real_pidfd_signal_closes_owned_fixture_and_original_parent_records_exit(self):
        scratch = ROOT / ".studio/hero-stop-tests"
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as temporary:
            root = Path(temporary)
            parent = root / "projects/hero-sandbox/manage.py"
            parent.parent.mkdir(parents=True)
            child = root / "owned_child.py"
            project = root / "Lyra.uproject"
            game_map = "/NovanodeHeroes/Maps/L_HeroSandbox_v2"
            job = "play-v2-abcdefabcdef"
            journal = root / ".studio/evidence" / f"hero-sandbox-job-{job}.json"
            child.write_text('''import signal, sys, time
from pathlib import Path
folder = Path(__file__).parent
def close(signum, frame):
    (folder / 'signal.txt').write_text(str(signum))
    raise SystemExit(0)
signal.signal(signal.SIGINT, close)
(folder / 'ready.txt').write_text('ready')
deadline = time.monotonic() + 4
while time.monotonic() < deadline:
    time.sleep(.01)
raise SystemExit(7)
''')
            parent.write_text(f'''import datetime, json, subprocess, sys, time
from pathlib import Path
root = Path({str(root)!r})
command = [sys.executable, str(root / 'owned_child.py'), {str(project)!r}, {game_map!r}, '-game']
started = datetime.datetime.now(datetime.timezone.utc).isoformat()
process = subprocess.Popen(command)
deadline = time.monotonic() + 3
while not (root / 'ready.txt').exists() and time.monotonic() < deadline:
    time.sleep(.01)
ticks = Path(f'/proc/{{process.pid}}/stat').read_text().rsplit(')', 1)[1].split()[19]
path = Path({str(journal)!r})
path.parent.mkdir(parents=True)
row = {{'job_id': {job!r}, 'operation': 'play-v2', 'state': 'running_unknown', 'pid': process.pid,
       'process_start_ticks': ticks, 'started_at': started, 'command': command, 'human_approval': 'pending'}}
reservation = path.with_suffix('.reservation')
reservation.write_text(json.dumps(row))
reservation.replace(path)
code = process.wait()
row.update(state='completed' if code == 0 else 'blocked', exit_code=code,
           finished_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
           summary={{'normal_exit_marker': code == 0}})
temporary = path.with_suffix('.pending')
temporary.write_text(json.dumps(row))
temporary.replace(path)
''')
            with (root / "fixture-console.log").open("wb") as log:
                wrapper = subprocess.Popen([sys.executable, str(parent), "play-v2"], stdout=log, stderr=log)
                try:
                    deadline = time.monotonic() + 3
                    while not journal.exists() and time.monotonic() < deadline:
                        time.sleep(.01)
                    self.assertTrue(journal.exists(), "Owned fixture launcher did not reserve a job")
                    result = hero_stop.stop_session(root, Path(sys.executable), project, game_map, timeout=3)
                    self.assertEqual(result["state"], "stopped")
                    self.assertEqual(result["native_exit_code"], 0)
                    self.assertEqual((root / "signal.txt").read_text(), str(signal.SIGINT))
                    self.assertEqual(wrapper.wait(timeout=3), 0)
                    self.assertEqual(load_json(journal)["state"], "completed")
                    self.assertFalse(result["native_success_verified"])
                finally:
                    # Finite owned fixture ends on its own; no SIGKILL/group signal fallback.
                    if wrapper.poll() is None:
                        wrapper.wait(timeout=10)
