import copy
import json
import shutil
from unittest.mock import patch

from helpers import ProjectTest
from pipeline.common import ROOT, StudioError
from pipeline.models import fetch, free_coding_models, local_record, memory_plan, opencode_profile, probe, serve_argv


class ModelTests(ProjectTest):
    def setUp(self):
        super().setUp()
        shutil.copy(ROOT / "models.lock.json", self.root / "models.lock.json")

    def candidate(self):
        return {"id": "vendor/coder:free", "name": "Coder", "pricing": {"prompt": "0", "completion": "0", "request": "0"},
                "architecture": {"output_modalities": ["text"]}, "supported_parameters": ["tools"]}

    def test_free_filter_requires_text_tools_and_all_zero_prices(self):
        valid = self.candidate()
        invalid = []
        for field, value in [("id", "vendor/paid"), ("supported_parameters", []),
                             ("architecture", {"output_modalities": ["audio"]}),
                             ("pricing", {"prompt": "0", "completion": "0", "request": "0.08"}),
                             ("pricing", {"prompt": "NaN", "completion": "0"}),
                             ("pricing", {"prompt": "0", "completion": "-1"})]:
            model = copy.deepcopy(valid)
            model[field] = value
            invalid.append(model)
        result = free_coding_models({"data": invalid + [valid]})
        self.assertEqual([row["id"] for row in result], [valid["id"]])

    def test_editor_reserve_rejects_large_model_but_allows_small_candidate(self):
        large = memory_plan(local_record("qwen38-main", self.root), "editor", 24)
        small = memory_plan(local_record("qwen35-small", self.root), "editor", 19)
        self.assertFalse(large["fits_estimate"])
        self.assertTrue(small["fits_estimate"])
        self.assertEqual(large["editor_reserve_gib"], 8)

    def test_solo_estimate_keeps_runtime_headroom(self):
        plan = memory_plan(local_record("qwen38-main", self.root), "solo", 24)
        self.assertTrue(plan["fits_estimate"])
        self.assertEqual(plan["runtime_estimate_gib"], 3)

    def test_download_is_opt_in_and_immutable_revision(self):
        with patch("pipeline.models.verified_download") as download:
            result = fetch("qwen38-main", root=self.root)
            download.assert_not_called()
        self.assertEqual(result["status"], "dry_run")
        self.assertNotIn("/main/", result["url"])
        self.assertEqual(len(result["sha256"]), 64)

    def test_serving_is_local_single_slot_with_bounded_context(self):
        argv = serve_argv("qwen35-small", self.root)
        self.assertEqual(argv[argv.index("--host") + 1], "127.0.0.1")
        self.assertEqual(argv[argv.index("--parallel") + 1], "1")
        self.assertEqual(argv[argv.index("--ctx-size") + 1], "16384")

    def test_free_profile_has_zero_price_caps_and_no_other_provider_fallback(self):
        profile = opencode_profile("free", root=self.root)
        caps = profile["providers"]["openrouter"]["body"]["provider"]["max_price"]
        self.assertTrue(all(value == 0 for value in caps.values()))
        self.assertEqual(profile["providers"]["openrouter"]["body"]["provider"]["data_collection"], "deny")
        self.assertEqual(profile["policies"][0], {"action": "provider.use", "resource": "*", "effect": "deny"})
        self.assertTrue(profile["model"].endswith(":free"))
        declared = profile["providers"]["openrouter"]["models"]
        self.assertEqual(declared["cohere/north-mini-code:free"]["capabilities"]["input"], ["text"])
        self.assertIn("image", declared["nvidia/nemotron-3.5-super-vl:free"]["capabilities"]["input"])

    def test_profiles_use_v2_fields_and_never_embed_keys(self):
        for name in ("free", "local"):
            profile = opencode_profile(name, root=self.root)
            for deprecated in ("provider", "permission", "enabled_providers", "disabled_providers"):
                self.assertNotIn(deprecated, profile)
            text = json.dumps(profile)
            self.assertNotIn('"npm"', text)
            self.assertNotIn('"options"', text)
            self.assertNotIn("sk-or-", text)

    def test_local_profile_does_not_advertise_unloaded_vision_encoder(self):
        profile = opencode_profile("local", "qwen38-main", self.root)
        model = next(iter(profile["providers"]["novanode-local"]["models"].values()))
        self.assertEqual(model["capabilities"]["input"], ["text"])
        self.assertEqual(model["limit"]["context"], 16384)

    def test_unknown_model_is_rejected(self):
        with self.assertRaises(StudioError):
            local_record("invented", self.root)

    def test_probe_is_opt_in(self):
        with patch("pipeline.models._local_completion") as request:
            self.assertEqual(probe("qwen35-small", root=self.root)["status"], "dry_run")
            request.assert_not_called()

    def test_probe_checks_both_tool_call_and_result_round_trip(self):
        first = {"choices": [{"message": {"role": "assistant", "content": None, "tool_calls": [
            {"id": "probe-1", "type": "function", "function": {"name": "novanode_probe", "arguments": "{\"value\":42}"}}
        ]}}]}
        second = {"choices": [{"message": {"role": "assistant", "content": "PROBE_OK"}}]}
        with patch("pipeline.models._local_completion", side_effect=[first, second]) as request:
            result = probe("qwen35-small", execute=True, root=self.root)
            self.assertEqual(request.call_count, 2)
        self.assertEqual(result["status"], "machine_verified")
        self.assertIn("not coding quality", result["scope"])

    def test_probe_rejects_prose_instead_of_a_tool_call(self):
        with patch("pipeline.models._local_completion", return_value={"choices": [{"message": {"content": "I would call the tool"}}]}):
            with self.assertRaises(StudioError):
                probe("qwen35-small", execute=True, root=self.root)
