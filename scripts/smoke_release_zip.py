"""Smoke-test the *built ZIP* in a disposable Codex/MCP workspace.

This is a local process/protocol smoke test, NOT real IDE acceptance.
Never modifies a non-temporary user project, host configuration, or release.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def smoke(root=ROOT):
    version = (root / "VERSION").read_text(encoding="utf-8").strip()
    archive = root / "dist" / ("ORBIT-Universal-Setup-v" + version + ".zip")
    checksum = root / "dist" / (archive.name + ".sha256")
    actual = hashlib.sha256(archive.read_bytes()).hexdigest()
    claimed = checksum.read_text(encoding="utf-8").split()[0]
    if actual != claimed:
        raise RuntimeError("Candidate release ZIP checksum mismatch")

    with tempfile.TemporaryDirectory(prefix="orbit-zip-smoke-") as folder:
        temporary = Path(folder)
        prefix = "orbit-universal-" + version
        with zipfile.ZipFile(archive) as z:
            names = z.namelist()
            if not names or len(names) != len(set(names)):
                raise RuntimeError("Candidate archive inventory invalid")
            if any(not n.startswith(prefix + "/") or ".." in Path(n).parts
                   or "\\" in n or n.startswith("/") for n in names):
                raise RuntimeError("Candidate archive has an unsafe member path")
            z.extractall(temporary)
        pkg = temporary / prefix
        if (pkg / "VERSION").read_text(encoding="utf-8").strip() != version:
            raise RuntimeError("Extracted VERSION differs from release archive")
        bundle = pkg / ("ORBIT-Claude-Desktop-v" + version + ".mcpb")
        with zipfile.ZipFile(bundle) as z:
            if json.loads(z.read("manifest.json")).get("version") != version:
                raise RuntimeError("Desktop manifest VERSION mismatch")
            for path in (pkg / "source/runtime").glob("*.py"):
                if z.read("server/" + path.name) != path.read_bytes():
                    raise RuntimeError("Packaged server/source mismatch: " + path.name)

        for file in ("orbit_setup.py", "Orbit Setup.cmd"):
            if not (pkg / file).is_file():
                raise RuntimeError("Unified setup launcher missing from candidate ZIP: " + file)
        workspace = temporary / "disposable-project"
        workspace.mkdir()
        home = temporary / "isolated-home"
        home.mkdir()
        env = {**os.environ, "ORBIT_SETUP_HOME": str(home),
               "ORBIT_LOCAL_DB": str(temporary / "memory.sqlite3")}
        command = [sys.executable, str(pkg / "installer.py"),
                   "--scope", "project", "--project", str(workspace),
                   "--hosts", "codex"]
        preview = subprocess.run(command, capture_output=True, text=True, timeout=25, env=env)
        if preview.returncode != 0 or "PREVIEW ONLY" not in preview.stdout:
            raise RuntimeError("Candidate installer preview failed: " + preview.stderr)
        if list(workspace.iterdir()):
            raise RuntimeError("Candidate installer preview modified the disposable project")
        apply = subprocess.run(command + ["--install"], capture_output=True, text=True,
                               timeout=25, env=env)
        if apply.returncode != 0:
            raise RuntimeError("Candidate disposable install failed: " + apply.stderr)
        server = home / ".orbit-universal" / version / "orbit_mcp.py"
        if not server.is_file() or server.read_bytes() != (pkg / "source/runtime/orbit_mcp.py").read_bytes():
            raise RuntimeError("Installed MCP source differs from candidate")
        calls = [
            {"jsonrpc":"2.0","id":1,"method":"initialize",
             "params":{"protocolVersion":"2025-11-25","capabilities":{},"clientInfo":{"name":"zip-smoke","version":"1"}}},
            {"jsonrpc":"2.0","id":2,"method":"tools/list"},
            {"jsonrpc":"2.0","id":3,"method":"tools/call",
             "params":{"name":"orbit_project_resume",
                       "arguments":{"project_root":str(workspace),"project":"orbit-zip-smoke"}}},
            {"jsonrpc":"2.0","id":4,"method":"tools/call",
             "params":{"name":"orbit_software_delivery_preview",
                       "arguments":{"project_root":str(workspace),"project":"orbit-zip-smoke",
                                    "product_type":"web-app","operation":"build","maturity":"new",
                                    "objective":"Create a disposable end-to-end test application"}}},
        ]
        result = subprocess.run([sys.executable, str(server)],
                                input="".join(json.dumps(msg)+"\n" for msg in calls),
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, timeout=30, env=env)
        if result.returncode != 0:
            raise RuntimeError("Packaged MCP server failed: " + result.stderr[-1600:])
        replies = [json.loads(line) for line in result.stdout.splitlines()]
        if len(replies) != 4 or any("error" in reply for reply in replies):
            raise RuntimeError("Invalid packaged MCP JSON-RPC results")
        tools = {tool["name"] for tool in replies[1]["result"]["tools"]}
        expected = {"orbit_project_resume", "orbit_project_action", "orbit_memory_recall",
                    "orbit_project_checkpoint", "orbit_build_begin", "orbit_swarm_preview", "orbit_swarm_draft_preview", "orbit_swarm_host_preflight", "orbit_swarm_integration_review", "orbit_software_delivery_preview"}
        if not expected.issubset(tools) or len(tools) != 47:
            raise RuntimeError("Packaged MCP tool inventory mismatch")
        if replies[2]["result"].get("isError"):
            raise RuntimeError("Packaged resume returned tool error")
        response = replies[3]["result"]
        if response.get("isError"):
            raise RuntimeError("Packaged delivery blueprint returned tool error")
        content = response.get("content", [])
        if not content or content[0].get("type") != "text":
            raise RuntimeError("No delivery blueprint content in MCP response")
        parsed = json.loads(content[0]["text"])
        if (parsed.get("status") != "BLUEPRINT_READY"
                or parsed.get("agent_spawned") is not False
                or parsed.get("state_written") is not False):
            raise RuntimeError("Packaged delivery preview failed read-only gate")

        uninstall = subprocess.run([sys.executable, str(pkg / 'orbit_setup.py'), 'uninstall',
                                   '--scope', 'project', '--project', str(workspace),
                                   '--hosts', 'codex', '--apply'],capture_output=True,text=True,
                                   timeout=25,env=env)
        if uninstall.returncode != 0 or 'Uninstalled' not in uninstall.stdout:
            raise RuntimeError('Unified setup uninstall smoke failed: '+uninstall.stderr)
        if 'orbit-core-native' in (workspace / '.codex/config.toml').read_text():
            raise RuntimeError('Unified setup left Codex Orbit MCP registration')
        if not server.is_file():
            raise RuntimeError('Uninstall removed shared Orbit MCP runtime')
        return {"version": version, "sha256": actual, "tools": len(tools),
                "result": "DISPOSABLE_INSTALL_AND_STDIO_SMOKE_PASS",
                "note": "No real IDE, desktop UI or browser has been tested"}


if __name__ == "__main__":
    print(json.dumps(smoke(), indent=2))
