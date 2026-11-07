"""Original frontend additive integration policy: no engine or UI launch."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

from pipeline.common import ROOT
from pipeline import hero_play

PROJECT = ROOT / "projects/hero-sandbox"
SOURCE = PROJECT / "NovanodeTraining/Source/NovanodeTraining"
spec = importlib.util.spec_from_file_location("native_original_under_test", PROJECT / "native_frontend.py")
frontend = importlib.util.module_from_spec(spec)
spec.loader.exec_module(frontend)


class NativeFrontendTests(unittest.TestCase):
    def test_default_entry_and_return_are_original_lyra_not_replacement(self):
        argv = hero_play.command(ROOT, hero_play.ENGINE)
        self.assertEqual(argv[2], "/Game/System/FrontEnd/Maps/L_LyraFrontEnd")
        self.assertIn("GameDefaultMap=" + argv[2], " ".join(argv))
        self.assertIn("-NovanodeNativeFrontend", argv)
        self.assertNotIn("L_TrainingLobby", " ".join(argv))
        self.assertNotIn("-ResX=1280", argv)

    def test_native_host_lifecycle_does_not_require_custom_lobby_actual_cpp(self):
        scratch = ROOT / ".studio/runs/native-frontend-tests"
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as folder:
            folder = Path(folder)
            source = folder / "flow.cpp"
            source.write_text('''#include "TrainingFlow.h"
#include <cassert>
int main() {
    using namespace NovanodeTraining;
    Flow f;
    assert(f.BeginNativeMatch());
    assert(f.MatchGeneration == 1 && f.Selected == Hero::None);
    assert(!f.BeginNativeMatch());
    assert(!f.MatchReady(true, 2));
    assert(f.MatchReady(true, 3));
    f.Selected = Hero::Melee;
    assert(f.Return());
    assert(f.BeginNativeMatch());
    assert(f.MatchGeneration == 2 && f.Selected == Hero::None);
    assert(f.MatchReady(true, 3));
    f.Selected = Hero::Mage;
    assert(f.Return());
}
''')
            binary = folder / "flow"
            subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-I", str(SOURCE / "Public"),
                            str(source), "-o", str(binary)], check=True, capture_output=True, timeout=20)
            subprocess.run([str(binary)], check=True, timeout=5)

    def test_native_phase_commands_use_normal_registration_and_no_asset_recipe(self):
        for operation in ("schema", "verify"):
            argv = frontend.command(operation, ROOT / ".studio/builds/TEST")
            self.assertIn("-NullRHI", argv)
            self.assertNotIn("SkipBuiltInGameFeatures", " ".join(argv))
            self.assertNotIn("prepare_native_training.py", " ".join(argv))
            self.assertIn("/Game/System/FrontEnd/Maps/L_LyraFrontEnd", argv)
        self.assertNotIn("-DisablePython", frontend.command("schema", ROOT))
        self.assertIn("-DisablePython", frontend.command("verify", ROOT))

    def test_prior_loop_result_cannot_count_as_native_original_frontend_proof(self):
        match = dict(total_bots=3, owned_bots=3, ready_bots=3, rival_bots=3, match_components=1,
                     human_team=1, rival_team=2, human_ready=True)
        result = dict(passed=True, ready_matches=2, generation=2, lobby_arrivals=3, native_returns=2,
                      cleanups=2, cleanup_valid=True, matches=[match, dict(match)])
        self.assertFalse(frontend.verified_result(result))
        native = {**result, "native_frontend": True, "native_menu_callbacks": 2,
                  "native_experience_callbacks": 2, "native_host_callbacks": 2}
        self.assertTrue(frontend.verified_result(native))
        self.assertFalse(frontend.verified_result({**native, "native_host_callbacks": 1}))

    def test_owned_definition_is_configured_in_memory_never_saved(self):
        source = (SOURCE / "Private/TrainingNativeFrontend.cpp").read_text()
        self.assertIn("DA_HeroTraining.DA_HeroTraining", source)
        self.assertNotRegex(source, r"\b(?:SavePackage|SavePackages|MarkPackageDirty)\s*\(")
        self.assertIn('TEXT("TileTitle")', source)
        self.assertIn("ObjectParameter", source)
        self.assertIn("Argument->IsA(Parameter->PropertyClass)", source)

    def test_selector_reuses_lyra_button_and_native_route_skips_custom_escape(self):
        lobby = (SOURCE / "Private/TrainingLobby.cpp").read_text()
        match = (SOURCE / "Private/TrainingMatchComponent.cpp").read_text()
        self.assertIn("/Game/UI/Menu/W_LyraMenuButton.W_LyraMenuButton_C", lobby)
        self.assertNotIn("ConstructWidget<UButton>", lobby)
        self.assertIn("Button->OnClicked().Add(Delegate)", lobby)
        self.assertIn("!Session->UsesNativeFrontend()", match)
        self.assertIn("Session->NativeMatchStarted()", match)
        self.assertIn("ReleaseNativeSelectionPause();", lobby)

    def test_native_select_start_finishes_existing_match_without_second_host(self):
        lobby = (SOURCE / "Private/TrainingLobby.cpp").read_text()
        start = lobby.split("bool UTrainingLobbySubsystem::Host()", 1)[1]
        native = start.split("if (!GetWorld()", 1)[0]
        self.assertIn("if (bNativeChoosing)", native)
        self.assertNotIn("Sessions->HostSession", native)
        self.assertIn("Flow.Selected == NovanodeTraining::Hero::None", native)

    def test_probe_only_driver_not_production_tick_or_global_overlay(self):
        source = (SOURCE / "Private/TrainingNativeFrontend.cpp").read_text()
        self.assertIn("ProbePath.IsEmpty()", source.split("void UTrainingLobbySubsystem::NativeProbeStep()", 1)[1])
        self.assertNotIn("AddToViewport", source)
        self.assertNotIn("Tick(", source)


if __name__ == "__main__":
    unittest.main()
