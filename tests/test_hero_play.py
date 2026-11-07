"""Manual launcher tests: no engine, GPU, window or signals."""
from contextlib import ExitStack, nullcontext
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from pipeline import hero_play
from pipeline.cli import dispatch, parser
from pipeline.common import ROOT, StudioError


class HeroPlayTests(unittest.TestCase):
    def setUp(self):
        scratch = ROOT / ".studio/runs/hero-play-tests"
        scratch.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=scratch)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.engine = self.root / "engine"

    def test_command_uses_absolute_paths_and_native_lobby_not_probe(self):
        argv = hero_play.command(self.root, self.engine)
        self.assertTrue(Path(argv[0]).is_absolute())
        self.assertEqual(argv[1], str(self.root / ".studio/lyra/projects/LyraStarterGame/Lyra.uproject"))
        self.assertEqual(argv[2], hero_play.LOBBY)
        self.assertIn("-game", argv)
        self.assertIn("-fullscreen", argv)
        self.assertIn("-DPCVars=r.FullScreenMode=1", argv)
        self.assertIn("-NovanodeNativeFrontend", argv)
        self.assertNotIn("-ResX=1280", argv)
        self.assertNotIn("/NovanodeTraining/Maps/L_TrainingLobby", argv)
        self.assertFalse(any(x in " ".join(argv) for x in ("Probe=", "NullRHI", "unattended", "SkipBuiltInGameFeatures")))
        overrides = next(x for x in argv if x.startswith("-ini:Engine:"))
        for expected in ("DefaultPlatformService=Null", "DefaultServices=Null", "bRemoteExecution=False",
                         "bAllowNetworkConnection=False", "GameDefaultMap=" + hero_play.LOBBY):
            self.assertIn(expected, overrides)

    def test_preview_has_no_process_locks_gpu_or_disk_side_effects(self):
        with patch.object(hero_play.subprocess, "Popen") as spawn, patch.object(hero_play.subprocess, "run") as run, \
                patch.object(hero_play, "resource_lock") as lock:
            result = hero_play.play(root=self.root, engine=self.engine)
        self.assertEqual(result["status"], "preview")
        self.assertEqual(result["cwd"], str(self.root.resolve()))
        self.assertEqual(result["environment_overrides"]["UE-SharedDataCachePath"], "None")
        self.assertEqual(list(self.root.iterdir()), [])
        spawn.assert_not_called()
        run.assert_not_called()
        lock.assert_not_called()

    def test_cli_requires_explicit_execute(self):
        for flags, expected in (([], False), (["--execute"], True)):
            with patch.object(hero_play, "play", return_value={}) as play:
                dispatch(parser().parse_args(["hero", "play", *flags]))
            play.assert_called_once_with(expected)

    def test_absolute_cli_path_works_from_another_directory(self):
        result = subprocess.run(["python3", str(ROOT / "studio.py"), "hero", "play"], cwd=self.root,
                                capture_output=True, text=True, check=True, timeout=10)
        preview = json.loads(result.stdout)
        self.assertEqual(preview["cwd"], str(ROOT))
        self.assertEqual(preview["command"][1], str(ROOT / ".studio/lyra/projects/LyraStarterGame/Lyra.uproject"))
        self.assertEqual(list(self.root.iterdir()), [])

    def installed(self):
        argv = hero_play.command(self.root, self.engine)
        stage = self.root / ".studio/lyra/projects/LyraStarterGame/Plugins/GameFeatures/NovanodeTraining"
        for path in (Path(argv[0]), Path(argv[1]), stage / "NovanodeTraining.uplugin",
                     stage / "Binaries/Linux/libUnrealEditor-NovanodeTraining.so",
                     stage / "Binaries/Linux/UnrealEditor.modules",
                     self.root / ".studio/lyra/projects/LyraStarterGame/Content/System/FrontEnd/Maps/L_LyraFrontEnd.umap",
                     stage / "Content/Maps/L_HeroTraining.umap", stage / "Content/Experiences/DA_HeroTraining.uasset"):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch()
        Path(argv[0]).chmod(0o700)
        return argv

    def test_preflight_missing_files_never_starts_or_queries_gpu(self):
        with patch.object(hero_play.subprocess, "run") as gpu, self.assertRaises(StudioError):
            hero_play.prerequisites(self.root, hero_play.command(self.root, self.engine))
        gpu.assert_not_called()

    def test_preflight_rejects_pending_jobs_and_existing_editor(self):
        argv = self.installed()
        evidence = self.root / ".studio/evidence"
        evidence.mkdir()
        receipt = evidence / "hero-native-manual-job-play-123.json"
        for state in ("reserved", "running_unknown", "outcome_unknown"):
            receipt.write_text(json.dumps({"state": state}))
            with self.assertRaisesRegex(StudioError, "Unfinished"):
                hero_play.prerequisites(self.root, argv)
        receipt.unlink()
        with patch.object(hero_play, "active_editors", return_value=[42]), self.assertRaisesRegex(StudioError, "already open"):
            hero_play.prerequisites(self.root, argv)

    def test_preflight_gpu_and_graphical_session_gates(self):
        argv = self.installed()
        with patch.object(hero_play, "active_editors", return_value=[]), \
                patch.dict(os.environ, {"DISPLAY": "", "WAYLAND_DISPLAY": ""}), self.assertRaisesRegex(StudioError, "graphical"):
            hero_play.prerequisites(self.root, argv)
        with patch.object(hero_play, "active_editors", return_value=[]), patch.dict(os.environ, {"DISPLAY": ":0"}), \
                patch.object(hero_play.subprocess, "run", return_value=Mock(stdout="1000\n")), \
                self.assertRaisesRegex(StudioError, "VRAM"):
            hero_play.prerequisites(self.root, argv)
        with patch.object(hero_play, "active_editors", return_value=[]), patch.dict(os.environ, {"DISPLAY": ":0"}), \
                patch.object(hero_play.subprocess, "run", return_value=Mock(stdout="12000\n")):
            hero_play.prerequisites(self.root, argv)

    def test_gpu_query_failure_is_an_actionable_error(self):
        argv = self.installed()
        with patch.object(hero_play, "active_editors", return_value=[]), patch.dict(os.environ, {"DISPLAY": ":0"}), \
                patch.object(hero_play.subprocess, "run", side_effect=subprocess.CalledProcessError(1, "nvidia-smi")), \
                self.assertRaisesRegex(StudioError, "Cannot confirm GPU"):
            hero_play.prerequisites(self.root, argv)

    def mocked_launch(self, code=0, wait_error=None):
        stack = ExitStack()
        self.addCleanup(stack.close)
        stack.enter_context(patch.object(hero_play, "resource_lock", side_effect=lambda *a: nullcontext()))
        stack.enter_context(patch.object(hero_play, "prerequisites"))
        child = Mock(pid=999999999)
        child.wait.return_value = code
        child.poll.return_value = None if wait_error else code
        if wait_error:
            child.wait.side_effect = wait_error
        def spawn(argv, **kwargs):
            receipts = list((self.root / ".studio/evidence").glob("*.json"))
            self.assertEqual(len(receipts), 1)
            self.assertEqual(json.loads(receipts[0].read_text())["state"], "reserved")
            self.assertEqual(kwargs["cwd"], self.root)
            self.assertTrue(kwargs["start_new_session"])
            self.assertNotIn("shell", kwargs)
            self.assertEqual(kwargs["env"]["UE_SharedDataCachePath"], "None")
            self.assertTrue(any(x.startswith("-AbsLog=") for x in argv))
            return child
        stack.enter_context(patch.object(hero_play.subprocess, "Popen", side_effect=spawn))
        return child

    def test_launch_persists_reservation_pid_and_observed_exit(self):
        self.mocked_launch()
        result = hero_play.play(True, self.root, self.engine)
        row = json.loads(Path(result["receipt"]).read_text())
        self.assertEqual(row["state"], "completed")
        self.assertEqual(row["exit_code"], 0)
        self.assertEqual(row["pid"], 999999999)
        self.assertFalse(row["gameplay_verified"])

    def test_failed_exit_is_recorded_and_not_returned_as_success(self):
        self.mocked_launch(-11)
        with self.assertRaisesRegex(StudioError, "code -11"):
            hero_play.play(True, self.root, self.engine)
        row = json.loads(next((self.root / ".studio/evidence").glob("*.json")).read_text())
        self.assertEqual((row["state"], row["exit_code"]), ("blocked", -11))

    def test_interrupted_wait_retains_unknown_outcome_without_signal(self):
        child = self.mocked_launch(wait_error=KeyboardInterrupt())
        with self.assertRaisesRegex(StudioError, "No stop signal"):
            hero_play.play(True, self.root, self.engine)
        row = json.loads(next((self.root / ".studio/evidence").glob("*.json")).read_text())
        self.assertEqual(row["state"], "outcome_unknown")
        self.assertIsNone(row["exit_code"])
        child.kill.assert_not_called()
        child.terminate.assert_not_called()

    def test_active_editor_detection_uses_names_not_arguments(self):
        proc = self.root / "proc"
        for pid, name in ((10, "UnrealEditor"), (11, "python3"), (12, "LyraGame")):
            folder = proc / str(pid)
            folder.mkdir(parents=True)
            (folder / "comm").write_text(name)
        self.assertEqual(hero_play.active_editors(proc), [10, 12])
