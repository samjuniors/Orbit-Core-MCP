"""Upgrade rehearsal from an immutable supported prior Git tag to a candidate ZIP.

Runs only inside a disposable temporary folder. Does NOT touch real host apps,
user configuration, credentials, running services, or any published release.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def checked_run(command, env):
    process = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             text=True, env=env, timeout=45)
    if process.returncode:
        raise RuntimeError("Installer upgrade rehearsal failed: " + process.stderr[-1500:] +
                           "\n" + process.stdout[-1500:])
    return process.stdout


def test_upgrade(previous_root, candidate_root=ROOT):
    previous_root = Path(previous_root).resolve(strict=True)
    candidate_root = Path(candidate_root).resolve(strict=True)
    old_version = (previous_root / "VERSION").read_text(encoding="utf-8").strip()
    new_version = (candidate_root / "VERSION").read_text(encoding="utf-8").strip()
    supported_source_versions = {"0.24.1", "0.25.1", "0.26.0", "0.27.0"}
    reviewed_candidate_versions = {"0.25.0", "0.25.1", "0.26.0", "0.27.0", "0.27.1", "0.28.0"}
    if (old_version not in supported_source_versions
            or new_version not in reviewed_candidate_versions
            or tuple(map(int, new_version.split("."))) <= tuple(map(int, old_version.split(".")))):
        raise RuntimeError("Upgrade rehearsal must use a supported immutable prior tag and newer reviewed candidate")
    archive = candidate_root / "dist" / ("ORBIT-Universal-Setup-v" + new_version + ".zip")

    with tempfile.TemporaryDirectory(prefix="orbit-old-stock-upgrade-") as folder:
        base = Path(folder)
        project = base / "disposable-user-project"
        home = base / "isolated-user-home"
        project.mkdir()
        home.mkdir()
        env = {**os.environ,
               "ORBIT_SETUP_HOME": str(home),
               "ORBIT_LOCAL_DB": str(base / "old-memories.sqlite3")}
        old_command = [sys.executable, str(previous_root / "installer.py"),
                       "--scope", "project", "--hosts", "codex", "--project", str(project)]
        checked_run(old_command + ["--install"], env)
        old_runtime = home / ".orbit-universal" / old_version / "orbit_mcp.py"
        if not old_runtime.is_file():
            raise RuntimeError("Old installer did not install versioned runtime")
        old_runtime_digest = hashlib.sha256(old_runtime.read_bytes()).hexdigest()

        # These paths are vendor-created by the checked-out immutable prior
        # installer. Print only public stock hashes (never private user data)
        # to support an exact, narrow upgrade allowlist review.
        stock_roots = [
            home / ".orbit-universal" / "orbit_cli.py",
            project / ".agents" / "skills" / "orbit" / "SKILL.md",
        ]
        stock_roots.extend(sorted((project / ".agents" / "skills" / "orbit" / "references").glob("*.md")))
        stock_files = [{"file": str(p.relative_to(home)) if p.is_relative_to(home)
                        else str(p.relative_to(project)), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
                       for p in stock_roots if p.is_file()]
        print("PREVIOUS_OFFICIAL_STOCK_HASHES " + json.dumps(stock_files, sort_keys=True), flush=True)

        # Existing owner guidance/docs and checkpoint files must survive an
        # upgrade without silently replacing them.
        owner_note = project / "AGENTS.md"
        owner_note.write_text("# Custom user guidance\nKeep the old owners' rules.\n",
                              encoding="utf-8")
        state = project / ".orbit" / "STATE.md"
        state.parent.mkdir()
        state.write_text("Owner checkpoint and application state\n", encoding="utf-8")
        memory = base / "old-memories.sqlite3"
        memory.write_bytes(b"OWNER_DB_SENTINEL_NOT_A_REAL_DATABASE")
        before = {p: p.read_bytes() for p in (owner_note, state, memory)}

        with zipfile.ZipFile(archive) as z:
            z.extractall(base / "new-archive")
        pkg = base / "new-archive" / ("orbit-universal-" + new_version)
        new_command = [sys.executable, str(pkg / "installer.py"),
                       "--scope", "project", "--hosts", "codex", "--project", str(project)]
        # A tiny owner edit to an *official* installed Orbit file must still
        # stop the upgrade; exact stock digests never authorize edited content.
        protected = project / ".agents" / "skills" / "orbit" / "references" / "TASK-LIFECYCLE.md"
        if not protected.is_file():
            raise RuntimeError("Previous stock task lifecycle reference missing")
        original = protected.read_bytes()
        owner_edit = original + b"\n# Owner-specific workflow customization\n"
        protected.write_bytes(owner_edit)
        blocked = subprocess.run(new_command, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, text=True, env=env, timeout=45)
        if blocked.returncode == 0 or "INSTALL BLOCKED" not in (blocked.stderr + blocked.stdout):
            raise RuntimeError("Customized installed Orbit file must trigger explicit manual-review block")
        if protected.read_bytes() != owner_edit:
            raise RuntimeError("Blocked upgrade modified an owner-customized stock file")
        protected.write_bytes(original)  # Restore only this isolated fixture for stock upgrade.
        preview = checked_run(new_command, env)
        if "PREVIEW ONLY" not in preview:
            raise RuntimeError("Upgrader must preview before writing")
        if any(p.read_bytes() != content for p, content in before.items()):
            raise RuntimeError("Installer preview unexpectedly changed user data")
        applied = checked_run(new_command + ["--install"], env)
        if "Installed " not in applied:
            raise RuntimeError("No installation completion evidence")
        for p, content in before.items():
            if p.read_bytes() != content:
                raise RuntimeError("Upgrade overwrote owner data: " + p.name)
        if hashlib.sha256(old_runtime.read_bytes()).hexdigest() != old_runtime_digest:
            raise RuntimeError("Upgrade mutated immutable previous runtime")
        new_runtime = home / ".orbit-universal" / new_version / "orbit_mcp.py"
        if not new_runtime.is_file() or new_runtime.read_bytes() != (pkg / "source/runtime/orbit_mcp.py").read_bytes():
            raise RuntimeError("New version runtime installation mismatch")

        return {"from": old_version, "to": new_version,
                "result": "DISPOSABLE_STOCK_UPGRADE_PASS",
                "preserved": ["custom AGENTS.md", ".orbit/STATE.md",
                              "existing DB bytes", "v" + old_version + " runtime"],
                "note": "This is NOT an acceptance test in a real IDE or user profile"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--previous-root", required=True,
                        help="Existing checked-out immutable prior release Git tag")
    args = parser.parse_args()
    print(json.dumps(test_upgrade(args.previous_root), indent=2))
