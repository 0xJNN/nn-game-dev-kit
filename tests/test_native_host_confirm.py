"""Measured missing original native host-screen confirmation; no engine launch."""
from pathlib import Path
import unittest

from pipeline.common import ROOT

PRIVATE = ROOT / "projects/hero-sandbox/NovanodeTraining/Source/NovanodeTraining/Private"


class NativeHostConfirmTests(unittest.TestCase):
    def test_original_host_screen_has_its_own_callback_not_a_second_direct_host(self):
        source = (PRIVATE / "TrainingNativeFrontend.cpp").read_text()
        self.assertIn("/Game/UI/Menu/Experiences/W_HostSessionScreen.W_HostSessionScreen_C", source)
        self.assertIn("BndEvt__W_HostSessionScreen_W_ExperienceList_K2Node_ComponentBoundEvent_0_OnExperienceSelected__DelegateSignature", source)
        self.assertIn("Host, 3, NativeDefinition", source)
        self.assertNotIn("Sessions->HostSession", source)
        self.assertNotIn("OpenLevel", source)
        self.assertNotIn("ClientTravel", source)

    def test_offline_mode_is_enum_schema_checked_not_guessed_numeric_index(self):
        source = (PRIVATE / "TrainingNativeFrontend.cpp").read_text()
        self.assertIn('Enum->GetName() != TEXT("ECommonSessionOnlineMode")', source)
        self.assertIn('Enum->GetValueByNameString(TEXT("Offline"))', source)
        self.assertIn("Argument->IsA(Parameter->PropertyClass)", source)

    def test_native_loop_evidence_requires_two_final_offline_confirmations(self):
        source = (PRIVATE / "TrainingLobby.cpp").read_text()
        self.assertIn("NativeOfflineHostCallbacks == 2", source)
        self.assertIn('TEXT("native_offline_host_callbacks")', source)


if __name__ == "__main__":
    unittest.main()
