"""Small, explicit resource gate — not a marketplace scraper or a legal oracle.

Run `python3 -m pipeline.resources list` or `... fetch <id> --execute`.
Only reviewed, zero-price items can be fetched. Assets stay local and are never
sent to an AI service. First acquisition records a hash; subsequent bytes must
match the committed pin. Unknown or restrictive AI rights fail closed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
import urllib.parse
import urllib.request
import zipfile

from .common import ROOT, StudioError, atomic_json, load_json, project_path, utc_now

CATALOG = "resources/hero-sandbox/catalog.json"
LICENSES = {"CC0-1.0", "CC-BY-4.0"}
MAX_BYTES = 32 * 1024 * 1024
MEDIA = {".fbx", ".glb", ".obj", ".mtl", ".png", ".jpg", ".wav", ".ogg", ".txt", ".md"}


def validate_catalog(data):
    if data.get("schema_version") != 1 or not isinstance(data.get("items"), list):
        raise StudioError("Unsupported resource catalog")
    seen = set()
    for item in data["items"]:
        name = item.get("id", "")
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", name) or name in seen:
            raise StudioError("Invalid or duplicated resource ID")
        seen.add(name)
        for field in ("title", "author", "source_url", "license_url", "license_id", "license_evidence", "ai_input", "native_status", "notes"):
            if not isinstance(item.get(field), str) or not item[field].strip():
                raise StudioError(f"{name}: missing {field}")
        for field in ("source_url", "license_url", "license_evidence"):
            safe_url(item[field])
        if item["ai_input"] not in {"cc0_no_additional_restriction_found", "restricted", "unknown"}:
            raise StudioError("Unknown AI-input status")
        if item.get("sha256") is not None and not re.fullmatch(r"[0-9a-f]{64}", item["sha256"]):
            raise StudioError("Invalid artifact checksum")
    return data


def eligible(item, purpose="engine"):
    if purpose not in {"engine", "ai"}:
        raise StudioError("Unknown resource purpose")
    if item.get("review") != "reviewed_item" or item.get("price_usd") != "0.00":
        raise StudioError("Item/license/free tier has not been reviewed")
    if item.get("license_id") not in LICENSES:
        raise StudioError("License requires a separate review")
    if item["license_id"] == "CC-BY-4.0" and not item.get("attribution"):
        raise StudioError("CC-BY requires attribution")
    if purpose == "ai" and item.get("ai_input") != "cc0_no_additional_restriction_found":
        raise StudioError("AI input is restricted or unresolved; do not upload this asset")
    if item.get("account_required") is not False:
        raise StudioError("Account/terms flow requires the human")
    return True


def safe_url(url):
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise StudioError("Expected a public HTTPS URL without credentials")
    if parsed.hostname in {"localhost", "127.0.0.1", "::1"} or re.fullmatch(r"[\d.]+", parsed.hostname):
        raise StudioError("Local/IP URLs are not resource sources")
    return parsed


def approved_download_url(url):
    host = safe_url(url).hostname
    if host not in {"static.poly.pizza", "drive.google.com", "drive.usercontent.google.com", "quaternius.itch.io"} and not host.endswith(".r2.cloudflarestorage.com") and not host.endswith(".itch.zone"):
        raise StudioError("Download redirect host needs explicit review")


class ReviewedRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        approved_download_url(newurl)
        return super().redirect_request(request, fp, code, message, headers, newurl)


def request(url, data=None):
    approved_download_url(url)
    req = urllib.request.Request(url, data=data, headers={"User-Agent": "NovanodeStudio/0.1", "Referer": "https://quaternius.itch.io/"})
    return urllib.request.build_opener(ReviewedRedirect()).open(req, timeout=45)


def safe_extract(archive: Path, destination: Path):
    """Preflight the complete ZIP before writing. No executables or .blend scripts."""
    with zipfile.ZipFile(archive) as source:
        infos = source.infolist()
        if len(infos) > 1200 or sum(i.file_size for i in infos) > 256 * 1024 * 1024:
            raise StudioError("Archive exceeds expanded size/count budget")
        seen, selected = set(), []
        for info in infos:
            name = info.filename
            path = PurePosixPath(name)
            if path.is_absolute() or ".." in path.parts or "\\" in name or ":" in name or "\0" in name:
                raise StudioError("Unsafe archive path")
            if path.as_posix().casefold() in seen:
                raise StudioError("Duplicate/colliding archive member")
            seen.add(path.as_posix().casefold())
            if stat.S_ISLNK(info.external_attr >> 16):
                raise StudioError("Archive symlinks are refused")
            if info.file_size > MAX_BYTES or info.file_size / max(1, info.compress_size) > 200:
                raise StudioError("Archive member exceeds size/compression budget")
            if not info.is_dir() and path.suffix.lower() in MEDIA:
                selected.append(info)
        if destination.exists():
            raise StudioError("Extraction destination exists; preserve it rather than overwrite")
        destination.mkdir(parents=True)
        for info in selected:
            target = destination.joinpath(*PurePosixPath(info.filename).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as output:
                output.write(source.read(info))
        return [{"file": str(p.relative_to(destination)), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
                for p in sorted(destination.rglob("*")) if p.is_file()]


def fetch_item(item, root=ROOT):
    eligible(item, "engine")
    download = item.get("download")
    if not download:
        raise StudioError("No reviewed anonymous download route; keep as a candidate")
    folder = root / ".studio/downloads/hero-sandbox" / item["id"]
    if folder.exists():
        raise StudioError("Acquisition exists; reconcile receipt/checksum, never overwrite")
    url = download["url"]
    # This is the public free-file endpoint, not purchase/checkout or an account.
    # Ephemeral signed CDN URLs are used only in memory and never saved/logged.
    if download["kind"] == "itch_free_file":
        with request(url, data=b"") as response:
            result = json.load(response)
        url = result.get("url")
        if not url:
            raise StudioError("Free download is unavailable; no payment fallback")
    elif download["kind"] != "direct":
        raise StudioError("Unknown download adapter")
    filename = download["filename"]
    if Path(filename).name != filename or Path(filename).suffix not in {".zip", ".glb", ".fbx"}:
        raise StudioError("Unexpected artifact name/type")
    # Network errors are summarized by type by the CLI; signed URLs never leak.
    with request(url) as response:
        data = response.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise StudioError("Download exceeds 32 MiB budget")
    suffix = Path(filename).suffix
    if (suffix == ".zip" and not data.startswith(b"PK")) or (suffix == ".glb" and not data.startswith(b"glTF")) or (suffix == ".fbx" and not data.startswith((b"Kaydara FBX Binary", b"; FBX"))):
        raise StudioError("Download is not the expected media type")
    checksum = hashlib.sha256(data).hexdigest()
    if item.get("sha256") and checksum != item["sha256"]:
        raise StudioError("Artifact checksum changed; preserve and review")
    folder.mkdir(parents=True)
    artifact = folder / filename
    with artifact.open("xb") as output:
        output.write(data)
    receipt = {"schema_version": 1, "id": item["id"], "acquired_at": utc_now(), "source_url": item["source_url"],
               "license_evidence": item["license_evidence"], "license_id": item["license_id"],
               "file": str(artifact.relative_to(root)), "sha256": checksum, "bytes": len(data),
               "pin_state": "matched_reviewed_pin" if item.get("sha256") else "first_acquisition_recorded_not_vendor_authenticated",
               "ai_input": item["ai_input"], "sent_to_ai": False, "native_import_verified": False}
    atomic_json(folder / "receipt.json", receipt)
    if suffix == ".zip":
        receipt["extracted"] = safe_extract(artifact, folder / "media")
        atomic_json(folder / "receipt.json", receipt)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("list", "validate", "fetch"))
    parser.add_argument("id", nargs="?")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    catalog = validate_catalog(load_json(project_path(CATALOG)))
    if args.operation == "fetch":
        item = next((i for i in catalog["items"] if i["id"] == args.id), None)
        if item is None: raise StudioError("Unknown resource ID")
        eligible(item)
        if not args.execute:
            print(json.dumps({"state": "dry_run", "id": item["id"], "source": item["source_url"], "paid_fallback": False}))
        else:
            receipt = fetch_item(item)
            print(json.dumps({k: v for k, v in receipt.items() if k != "extracted"}, indent=2))
    else:
        print(json.dumps({"state": "catalog_schema_verified_not_legal_or_native_approval", "items": [
            {k: i[k] for k in ("id", "license_id", "review", "ai_input", "native_status")} for i in catalog["items"]]}, indent=2))


if __name__ == "__main__":
    try:
        main()
    except StudioError as exc:
        print(json.dumps({"state": "refused_preserve_and_review", "reason": str(exc)}))
        raise SystemExit(1)
    except Exception as exc:
        print(json.dumps({"state": "acquisition_unknown_preserve_and_reconcile", "error_type": type(exc).__name__}))
        raise SystemExit(1)
