"""axiom/kernel/store.py

Decentralized mod store client, catalog index fetcher, and cryptographically
verified mod package installer (Rules §1.2 & §6.12).
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any
import urllib.parse
import urllib.request
import zipfile

from axiom.config import load_config, save_config
from axiom.kernel.dependencies import check_mod_python_dependencies
from axiom.kernel.manifest import (
    ManifestError,
    ModManifest,
    load_manifest,
    load_manifest_from_archive,
)
from axiom.logger import logger


class StoreError(Exception):
    """Raised on store query, fetch, or resolution errors."""


class ModIntegrityError(StoreError):
    """Raised when a downloaded mod archive fails SHA-256 cryptographic verification (Rule §6.12)."""


@dataclass
class StoreModEntry:
    """Descriptor of a mod available in a store index."""

    id: str
    version: str
    axiom_api: int
    name: str
    description: str
    author: str
    download_url: str
    sha256: str
    dependencies: dict[str, str] = field(default_factory=dict)
    python_requires: list[str] = field(default_factory=list)
    provides: list[str] = field(default_factory=list)
    raw_data: dict[str, Any] = field(default_factory=dict)


def calculate_sha256(file_path: Path | str) -> str:
    """Compute the hexadecimal SHA-256 digest of a file in streaming chunks."""
    path = Path(file_path)
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def get_default_store_cache_path() -> Path:
    """Return cache file location for remote store index."""
    env_cache = os.environ.get("AXIOM_STORE_CACHE_PATH")
    if env_cache:
        return Path(env_cache).resolve()
    return (Path.home() / ".cache" / "AxiomAI" / "store_cache.json").resolve()


def fetch_store_index(
    repo_url: str | Path | None = None,
    cache_path: Path | str | None = None,
    refresh: bool = False,
) -> list[StoreModEntry]:
    """Fetch and parse store catalog index from remote URL or local path.

    Supports local file paths, file:// URIs, and http(s):// URLs.
    Caches results locally unless refresh=True.
    """
    cache_file = Path(cache_path).resolve() if cache_path else get_default_store_cache_path()

    # Use local cache if fresh and not explicitly refreshing
    if not refresh and repo_url is None and cache_file.is_file():
        try:
            cached_data = json.loads(cache_file.read_text(encoding="utf-8"))
            return _parse_index_json(cached_data)
        except Exception as err:
            logger.debug("Failed to read store cache from %s: %s", cache_file, err)

    if repo_url is None:
        # Default fallback to repo-bundled index if present, else empty or default URL
        local_dist_index = Path("dist/mods/store_index.json").resolve()
        if local_dist_index.is_file():
            raw_json = local_dist_index.read_text(encoding="utf-8")
        else:
            raw_json = json.dumps({"version": 1, "repository_name": "Local Store", "mods": []})
    else:
        url_str = str(repo_url).strip()
        parsed = urllib.parse.urlparse(url_str)
        if parsed.scheme in ("http", "https"):
            req = urllib.request.Request(url_str, headers={"User-Agent": "AxiomAI-Engine/1.0.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw_json = resp.read().decode("utf-8")
        elif parsed.scheme == "file":
            local_path = Path(urllib.request.url2pathname(parsed.path))
            raw_json = local_path.read_text(encoding="utf-8")
        else:
            local_path = Path(url_str).resolve()
            if not local_path.is_file():
                raise StoreError(f"Local store index file not found: {local_path}")
            raw_json = local_path.read_text(encoding="utf-8")

    data = json.loads(raw_json)
    entries = _parse_index_json(data)

    # Update cache
    try:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(raw_json, encoding="utf-8")
    except Exception as err:
        logger.debug("Failed to update store cache at %s: %s", cache_file, err)

    return entries


def _parse_index_json(data: dict[str, Any]) -> list[StoreModEntry]:
    """Parse raw dictionary into StoreModEntry list."""
    mods_list = data.get("mods", [])
    entries: list[StoreModEntry] = []
    for item in mods_list:
        if not isinstance(item, dict):
            continue
        mod_id = item.get("id")
        if not mod_id:
            continue
        entries.append(
            StoreModEntry(
                id=mod_id,
                version=str(item.get("version", "0.1.0")),
                axiom_api=int(item.get("axiom_api", 1)),
                name=str(item.get("name", mod_id)),
                description=str(item.get("description", "")),
                author=str(item.get("author", "")),
                download_url=str(item.get("download_url", "")),
                sha256=str(item.get("sha256", "")).lower().strip(),
                dependencies=dict(item.get("dependencies", {})),
                python_requires=list(item.get("python_requires", [])),
                provides=list(item.get("provides", [])),
                raw_data=item,
            )
        )
    return entries


def search_store(
    query: str,
    entries: list[StoreModEntry] | None = None,
    repo_url: str | Path | None = None,
) -> list[StoreModEntry]:
    """Search available mods matching query keywords."""
    if entries is None:
        entries = fetch_store_index(repo_url=repo_url)

    q = query.lower().strip()
    if not q:
        return list(entries)

    results: list[StoreModEntry] = []
    for e in entries:
        if (
            q in e.id.lower()
            or q in e.name.lower()
            or q in e.description.lower()
            or q in e.author.lower()
            or any(q in p.lower() for p in e.provides)
        ):
            results.append(e)
    return results


def _download_file(url: str, dest_path: Path) -> Path:
    """Download or copy a file from URL/file path to dest_path."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme in ("http", "https"):
        req = urllib.request.Request(url, headers={"User-Agent": "AxiomAI-Engine/1.0.0"})
        with urllib.request.urlopen(req, timeout=30) as resp, open(dest_path, "wb") as out:
            shutil.copyfileobj(resp, out)
    elif parsed.scheme == "file":
        src_path = Path(urllib.request.url2pathname(parsed.path))
        shutil.copy2(src_path, dest_path)
    else:
        src_path = Path(url).resolve()
        if not src_path.is_file():
            raise FileNotFoundError(f"File not found: {src_path}")
        shutil.copy2(src_path, dest_path)
    return dest_path


def install_mod_from_store(
    mod_id: str,
    version: str | None = None,
    dest_dir: Path | str = Path("mods"),
    repo_url: str | Path | None = None,
    enable: bool = True,
) -> Path:
    """Download, verify SHA-256, and install a mod from the store.

    Args:
        mod_id: Namespaced mod ID.
        version: Optional exact version string.
        dest_dir: Destination folder (default: mods/).
        repo_url: Optional index URL or file path.
        enable: Whether to enable the mod in AppConfig.

    Returns:
        Path of the installed mod directory.

    Raises:
        StoreError: If mod is not found in store index.
        ModIntegrityError: If downloaded file SHA-256 does not match store metadata.
    """
    entries = fetch_store_index(repo_url=repo_url)
    candidates = [e for e in entries if e.id == mod_id]
    if not candidates:
        raise StoreError(f"Mod '{mod_id}' was not found in the store repository.")

    if version:
        matched = [e for e in candidates if e.version == version]
        if not matched:
            raise StoreError(f"Version '{version}' for mod '{mod_id}' not found.")
        target_entry = matched[0]
    else:
        # Pick latest
        target_entry = candidates[0]

    with tempfile.TemporaryDirectory() as tmp_d:
        temp_axmod = Path(tmp_d) / f"{target_entry.id}.axmod"
        _download_file(target_entry.download_url, temp_axmod)

        # 1. Cryptographic SHA-256 verification (Rule §6.12)
        actual_sha256 = calculate_sha256(temp_axmod)
        expected_sha256 = target_entry.sha256.lower().strip()
        if actual_sha256.lower() != expected_sha256:
            raise ModIntegrityError(
                f"Cryptographic integrity verification failed for mod '{mod_id}'!\n"
                f"  Expected SHA-256: {expected_sha256}\n"
                f"  Computed SHA-256: {actual_sha256}\n"
                f"The archive may have been altered or corrupted during download."
            )

        # 2. Manifest and API check
        manifest = load_manifest_from_archive(temp_axmod)
        if manifest.axiom_api != 1:
            raise StoreError(
                f"Mod '{mod_id}' requires incompatible axiom_api version: {manifest.axiom_api}"
            )

        # 3. Check python dependencies (Decision D-7)
        missing_py = check_mod_python_dependencies(manifest)
        if missing_py:
            for w in missing_py:
                logger.warning("[PythonDeps] %s", w)

        # 4. Unpack into target destination
        target_dir = Path(dest_dir).resolve() / manifest.id
        if target_dir.exists():
            shutil.rmtree(target_dir)
        target_dir.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(temp_axmod, "r") as zf:
            zf.extractall(target_dir)

        # Also store the verified archive in dist/mods if available and installing to standard mods dir
        dist_dir = Path("dist/mods")
        if dist_dir.is_dir() and Path(dest_dir).resolve() == Path("mods").resolve():
            shutil.copy2(temp_axmod, dist_dir / f"{manifest.id}-{manifest.version}.axmod")

    # 5. Enable in configuration
    if enable:
        cfg = load_config()
        cfg.mod_settings.setdefault(manifest.id, {})["enabled"] = True
        save_config(cfg)

    logger.info("Successfully installed mod '%s' (v%s) to %s", manifest.id, manifest.version, target_dir)
    return target_dir


def publish_mod_to_store_spec(
    mod_path: Path | str,
    download_url: str = "",
    output_json: Path | str | None = None,
) -> dict[str, Any]:
    """Inspect a mod directory or archive, calculate its SHA-256, and produce a store index entry.

    Args:
        mod_path: Path to mod folder or .axmod file.
        download_url: Public URL where the archive will be hosted.
        output_json: Optional path to save or append this specification.

    Returns:
        Dictionary conforming to StoreModEntry JSON format.
    """
    path = Path(mod_path).resolve()
    temp_dir = None
    if path.is_dir():
        from axiom.cli.mods_cmd import pack_mod

        temp_dir = tempfile.TemporaryDirectory()
        archive_path = pack_mod(path, output_path=Path(temp_dir.name) / "package.axmod")
        manifest = load_manifest(path)
    elif path.is_file() and path.suffix in (".axmod", ".zip"):
        archive_path = path
        manifest = load_manifest_from_archive(path)
    else:
        raise ValueError(f"Invalid mod path: {path}")

    sha256_hash = calculate_sha256(archive_path)

    if temp_dir:
        temp_dir.cleanup()

    entry = {
        "id": manifest.id,
        "version": manifest.version,
        "axiom_api": manifest.axiom_api,
        "name": manifest.name,
        "description": manifest.description,
        "author": manifest.author,
        "download_url": download_url or f"https://mods.axiomai.org/downloads/{manifest.id}-{manifest.version}.axmod",
        "sha256": sha256_hash,
        "dependencies": {k: v.version_spec for k, v in manifest.dependencies.items()},
        "python_requires": manifest.python_requires,
        "provides": manifest.ordering.provides,
    }

    if output_json:
        out_p = Path(output_json).resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)
        if out_p.is_file():
            try:
                data = json.loads(out_p.read_text(encoding="utf-8"))
            except Exception:
                data = {"version": 1, "repository_name": "Axiom Mod Repository", "mods": []}
        else:
            data = {"version": 1, "repository_name": "Axiom Mod Repository", "mods": []}

        # Replace existing or append
        existing_index = next((i for i, m in enumerate(data.get("mods", [])) if m.get("id") == manifest.id and m.get("version") == manifest.version), None)
        if existing_index is not None:
            data["mods"][existing_index] = entry
        else:
            data.setdefault("mods", []).append(entry)

        out_p.write_text(json.dumps(data, indent=2), encoding="utf-8")

    return entry
