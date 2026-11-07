"""Read-only normal-registration native frontend schema commandlet; never saves assets."""
import json
import os
from pathlib import Path


def main():
    import unreal
    unreal.load_module("NovanodeTraining")
    result = json.loads(unreal.TrainingReflectionAdapter.inspect_native_frontend())
    Path(os.environ["NN_NATIVE_FRONTEND_OUTPUT"]).write_text(json.dumps(result, indent=2) + "\n")
    if result.get("state") != "native_frontend_schema_verified":
        raise RuntimeError("native_frontend_schema_blocked")


if __name__ == "__main__":
    main()
