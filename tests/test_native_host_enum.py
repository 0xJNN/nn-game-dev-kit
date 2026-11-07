"""Regression for the measured UE raw-pointer/TObjectPtr conditional ambiguity."""
from pathlib import Path
import subprocess
import tempfile
import unittest

from pipeline.common import ROOT


class NativeHostEnumTests(unittest.TestCase):
    def test_offline_probe_explicitly_extracts_enum_pointer_actual_cpp(self):
        source = ROOT / "projects/hero-sandbox/NovanodeTraining/Source/NovanodeTraining/Private/TrainingNativeFrontend.cpp"
        self.assertIn("ByteProperty->Enum.Get() : nullptr", source.read_text())
        scratch = ROOT / ".studio/runs/native-host-enum-test"
        scratch.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as folder:
            p = Path(folder) / "enum.cpp"
            p.write_text('''#include <cassert>
struct Enum {};
struct Ptr {
    Enum* Value;
    Ptr(Enum* value) : Value(value) {}
    operator Enum*() const { return Value; }
    Enum* Get() const { return Value; }
};
int main() {
    Enum e; Ptr wrapped(&e); Enum* raw = &e;
    Enum* selected = false ? raw : true ? wrapped.Get() : nullptr;
    assert(selected == &e);
}
''')
            binary = p.with_suffix("")
            subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", str(p), "-o", str(binary)],
                           check=True, capture_output=True, timeout=20)
            subprocess.run([str(binary)], check=True, timeout=5)
