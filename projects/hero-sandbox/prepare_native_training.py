"""Frozen commandlet recipe: only the narrow owned native adapter can create assets."""
import json
import os
from pathlib import Path


def main():
    import unreal

    # Verified in installed PyCore method-table metadata; not a guessed struct binding.
    unreal.load_module("NovanodeTraining")
    adapter = unreal.TrainingReflectionAdapter
    operation = os.environ["NN_TRAINING_OPERATION"]
    calls = {
        "schema": adapter.inspect_installed_schema,
        "prepare": adapter.prepare_owned_assets,
    }
    result = json.loads(calls[operation]())
    Path(os.environ["NN_TRAINING_OUTPUT"]).write_text(json.dumps(result, indent=2) + "\n")
    expected = "schema_verified" if operation == "schema" else "prepared"
    if result.get("state") != expected:
        raise RuntimeError("owned_native_training_gate_blocked")


if __name__ == "__main__":
    main()
