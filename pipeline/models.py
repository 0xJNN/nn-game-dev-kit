from __future__ import annotations

import json
import hashlib
import shutil
import socket
import subprocess
import time
import urllib.request
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .common import ROOT, StudioError, atomic_json, load_json, resource_lock, utc_now
from .tools import verified_download

GIB = 1024 ** 3


def free_coding_models(data: dict) -> list[dict]:
    """Avoid free-looking audio/image models and routes with nonzero ancillary prices."""
    selected = []
    for model in data.get("data", []):
        if not model.get("id", "").endswith(":free"):
            continue
        if "text" not in model.get("architecture", {}).get("output_modalities", []):
            continue
        if "tools" not in model.get("supported_parameters", []):
            continue
        prices = model.get("pricing", {})
        if "prompt" not in prices or "completion" not in prices:
            continue
        try:
            values = [Decimal(str(price)) for price in prices.values()]
            if not values or any(not value.is_finite() or value != 0 for value in values):
                continue
        except (InvalidOperation, TypeError, ValueError):
            continue
        selected.append({
            "id": model["id"], "name": model.get("name"),
            "context_length": model.get("context_length"), "pricing": prices,
            "input_modalities": model.get("architecture", {}).get("input_modalities", []),
            "tools_advertised": True,
        })
    return sorted(selected, key=lambda item: item["id"])


def refresh_free(root: Path = ROOT) -> dict:
    request = urllib.request.Request("https://openrouter.ai/api/v1/models",
                                     headers={"User-Agent": "Novanode-Studio/0.2"})
    with urllib.request.urlopen(request, timeout=30) as response:
        data = json.load(response)
    result = {"checked_at": utc_now(), "source": request.full_url,
              "scope": "public metadata, not a completion or benchmark", "models": free_coding_models(data)}
    atomic_json(root / ".studio/research/openrouter-free.json", result)
    return result


def local_record(model: str, root: Path = ROOT) -> dict:
    record = load_json(root / "models.lock.json")["local"].get(model)
    if record is None:
        raise StudioError(f"Unknown local profile: {model}")
    return record


def vram() -> dict:
    executable = shutil.which("nvidia-smi")
    if not executable:
        raise StudioError("nvidia-smi unavailable; cannot verify GPU headroom")
    result = subprocess.run([executable, "--query-gpu=name,memory.total,memory.free", "--format=csv,noheader,nounits"],
                            capture_output=True, text=True, timeout=10, check=True)
    rows = result.stdout.strip().splitlines()
    if len(rows) != 1:
        raise StudioError("Expected one NVIDIA GPU; explicitly review device selection for multi-GPU setups")
    name, total, free = [part.strip() for part in rows[0].split(",")]
    return {"name": name, "total_gib": int(total) / 1024, "free_gib": int(free) / 1024}


def memory_plan(record: dict, mode: str, free_gib: float) -> dict:
    if mode not in {"solo", "editor"}:
        raise StudioError("Mode must be solo or editor")
    # Conservative policy estimates, not measured KV/compute usage for a specific architecture.
    weights = record["bytes"] / GIB
    runtime = 3.0
    editor = 8.0 if mode == "editor" else 0.0
    required = weights + runtime + editor
    return {"weights_gib": round(weights, 2), "runtime_estimate_gib": runtime,
            "editor_reserve_gib": editor, "required_free_gib": round(required, 2),
            "available_gib": round(free_gib, 2), "fits_estimate": free_gib >= required,
            "warning": "Heuristic only. Context, graph buffers, other apps, and Unreal peaks must be measured."}


def serve_argv(model: str, root: Path = ROOT) -> list[str]:
    record = local_record(model, root)
    return ["llama-server", "--model", str(root / ".studio/models" / record["file"]),
            "--alias", record["alias"], "--host", "127.0.0.1", "--port", "8091",
            "--ctx-size", str(record["context"]), "--parallel", "1", "--n-gpu-layers", "99",
            "--jinja", "--flash-attn", "on", "--cache-type-k", "q8_0", "--cache-type-v", "q8_0"]


def plan(model: str, mode: str, root: Path = ROOT) -> dict:
    record = local_record(model, root)
    result = {"model": model, "record": record, "argv": serve_argv(model, root),
              "downloaded": (root / ".studio/models" / record["file"]).is_file(),
              "load_tested": False, "tool_call_tested": False, "mode": mode}
    try:
        result["gpu"] = vram()
        result["memory"] = memory_plan(record, mode, result["gpu"]["free_gib"])
    except (StudioError, subprocess.SubprocessError) as exc:
        result["memory_unverified"] = str(exc)
    return result


def fetch(model: str, execute=False, root: Path = ROOT) -> dict:
    record = local_record(model, root)
    url = f"https://huggingface.co/{record['repository']}/resolve/{record['revision']}/{record['file']}"
    result = {"status": "dry_run", "url": url, "bytes": record["bytes"], "sha256": record["sha256"]}
    if not execute:
        return result
    directory = root / ".studio/models"
    if not (directory / record["file"]).exists() and shutil.disk_usage(root).free < record["bytes"] + 4 * GIB:
        raise StudioError("Insufficient disk headroom for the model; no files deleted")
    with resource_lock("model-download", root):
        path = verified_download({"url": url, "sha256": record["sha256"]}, directory)
    return {"status": "download_verified_not_load_tested", "path": str(path)}


def serve(model: str, mode: str, execute=False, root: Path = ROOT) -> dict | int:
    result = plan(model, mode, root)
    if not execute:
        return {"status": "dry_run", **result}
    if not result.get("memory", {}).get("fits_estimate"):
        raise StudioError("Insufficient/unverified GPU headroom. Close applications yourself or use cloud; nothing was stopped.")
    if not result["downloaded"]:
        raise StudioError("Pinned GGUF is not downloaded; use `models fetch <profile> --execute` only after reviewing size")
    record = local_record(model, root)
    with (root / ".studio/models" / record["file"]).open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != record["sha256"]:
            raise StudioError("Local GGUF does not match its pinned checksum; refusing to load")
    executable = shutil.which("llama-server")
    if not executable:
        raise StudioError("Install a reviewed CUDA llama.cpp build with support for this model architecture")
    try:
        with socket.create_connection(("127.0.0.1", 8091), timeout=0.3):
            raise StudioError("Port 8091 is already in use; existing service left untouched")
    except (ConnectionRefusedError, socket.timeout):
        pass
    argv = result["argv"]
    argv[0] = executable
    with resource_lock("gpu-inference", root):
        # Human-controlled foreground service. No model requests are made automatically.
        return subprocess.call(argv, cwd=root)


def _local_completion(payload: dict) -> dict:
    request = urllib.request.Request(
        "http://127.0.0.1:8091/v1/chat/completions", data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.load(response)


def probe(model: str, execute=False, root: Path = ROOT) -> dict:
    record = local_record(model, root)
    if not execute:
        return {"status": "dry_run", "endpoint": "http://127.0.0.1:8091/v1/chat/completions",
                "model": record["alias"], "requests": 2, "note": "Synthetic tool transport check; no generated tool is executed."}
    started = time.monotonic()
    messages = [{"role": "user", "content": "Call novanode_probe with value 42. After the tool reply, output exactly PROBE_OK."}]
    first = _local_completion({
        "model": record["alias"], "messages": messages, "max_tokens": 1024,
        "tools": [{"type": "function", "function": {
            "name": "novanode_probe", "description": "Synthetic transport test only; no side effects.",
            "parameters": {"type": "object", "properties": {"value": {"type": "integer"}},
                           "required": ["value"], "additionalProperties": False},
        }}],
        "tool_choice": {"type": "function", "function": {"name": "novanode_probe"}},
    })
    try:
        message = first["choices"][0]["message"]
        calls = message["tool_calls"]
        if len(calls) != 1 or calls[0]["function"]["name"] != "novanode_probe":
            raise ValueError("Unexpected tool call")
        arguments = json.loads(calls[0]["function"]["arguments"])
        if arguments != {"value": 42} or type(arguments["value"]) is not int or not calls[0]["id"]:
            raise ValueError("Incorrect arguments or missing tool ID")
        # Pass back only standard message fields plus the runtime's reasoning field.
        assistant = {key: message[key] for key in ("role", "content", "tool_calls", "reasoning_content") if key in message}
        second = _local_completion({
            "model": record["alias"], "max_tokens": 1024,
            "messages": messages + [assistant, {"role": "tool", "tool_call_id": calls[0]["id"], "content": "{\"ok\":true}"}],
        })
        if second["choices"][0]["message"].get("content", "").strip() != "PROBE_OK":
            raise ValueError("Tool-result round trip did not complete")
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise StudioError(f"Local tool transport probe failed: {exc}") from exc
    result = {"status": "machine_verified", "scope": "local tool transport only, not coding quality or vision",
              "model": model, "seconds": round(time.monotonic() - started, 3),
              "usage": [first.get("usage"), second.get("usage")], "human_approval": "pending"}
    atomic_json(root / ".studio/evidence" / f"model-probe-{model}.json", result)
    return result


def opencode_profile(profile: str, local_model="qwen35-small", root: Path = ROOT) -> dict:
    catalog = load_json(root / "models.lock.json")
    permissions = [
        {"action": "read", "resource": "*", "effect": "allow"},
        {"action": "read", "resource": "*.env*", "effect": "deny"},
        {"action": "read", "resource": ".studio/receipts/*", "effect": "deny"},
        {"action": "read", "resource": ".studio/ledger*", "effect": "deny"},
        {"action": "shell", "resource": "*", "effect": "ask"},
        {"action": "edit", "resource": "*", "effect": "ask"},
        {"action": "external_directory", "resource": "*", "effect": "ask"},
        {"action": "subagent", "resource": "*", "effect": "deny"},
        {"action": "websearch", "resource": "*", "effect": "deny"},
        {"action": "experimental_image_generate", "resource": "*", "effect": "deny"},
    ]
    common = {
        "$schema": "https://opencode.ai/config.json", "permissions": permissions,
        "skills": ["./.cursor/skills"],
        "watcher": {"ignore": [".studio/**", "**/Binaries/**", "**/Intermediate/**", "**/Saved/**", "**/DerivedDataCache/**"]},
        "tool_output": {"max_lines": 160, "max_bytes": 12000},
    }
    if profile == "free":
        model_ids = list(catalog["cloud"].values())
        common.update({
            "model": "openrouter/" + catalog["cloud"]["coding"],
            "providers": {"openrouter": {
                "env": ["OPENROUTER_API_KEY"],
                "body": {"provider": {"max_price": {"prompt": 0, "completion": 0, "request": 0, "image": 0},
                                      "require_parameters": True, "data_collection": "deny"}},
                "models": {name: {
                    "limit": {"context": 65536, "output": 8192},
                    "capabilities": {"tools": True, "reasoning": {"supported": True},
                                     "input": ["text", "image"] if name == catalog["cloud"]["visual_review"] else ["text"],
                                     "output": ["text"]},
                } for name in model_ids},
            }},
            "compaction": {"auto": True, "keep": {"tokens": 6000}, "buffer": "20%"},
        })
        allowed_provider = "openrouter"
    elif profile == "local":
        record = local_record(local_model, root)
        common.update({
            "model": "novanode-local/" + record["alias"],
            "providers": {"novanode-local": {
                "name": "Novanode localhost llama.cpp",
                "package": "@opencode/ai/providers/openai-compatible",
                "settings": {"baseURL": "http://127.0.0.1:8091/v1"},
                "models": {record["alias"]: {
                    "modelID": record["alias"], "name": record["name"],
                    "capabilities": {"tools": True, "input": ["text"], "output": ["text"]},
                    "compatibility": {"reasoningField": "reasoning_content", "maxTokensField": "max_tokens"},
                    "limit": {"context": record["context"], "output": record["output"]},
                }},
            }},
            "compaction": {"auto": True, "keep": {"tokens": 3000}, "buffer": "20%"},
        })
        allowed_provider = "novanode-local"
    else:
        raise StudioError("Profile must be free or local")
    common["policies"] = [
        {"action": "provider.use", "resource": "*", "effect": "deny"},
        {"action": "provider.use", "resource": allowed_provider, "effect": "allow"},
        {"action": "mcp.use", "resource": "*", "effect": "deny"},
        {"action": "tool.use", "resource": "subagent:*", "effect": "deny"},
    ]
    return common
