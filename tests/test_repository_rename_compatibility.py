"""Canonical repository rename compatibility, without changing shipped host identities."""
from __future__ import annotations
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/"source/runtime"))
import installer
import orbit_cli
import orbit_mcp
import orbit_updates

REPOSITORY="samjuniors/Orbit-Core"
OLD_REPOSITORY="samjuniors/Orbit-Core-MCP"

def release(version="0.27.0"):
    name="ORBIT-Universal-Setup-v"+version+".zip"
    url="https://github.com/"+REPOSITORY+"/releases"
    return {"tag_name":"v"+version,"draft":False,"prerelease":True,
        "name":"Orbit Core "+version,
        "body":"Published prerelease",
        "html_url":url+"/tag/v"+version,
        "assets":[{"name":name,"browser_download_url":url+"/download/v"+version+"/"+name},
                  {"name":name+".sha256","browser_download_url":url+"/download/v"+version+"/"+name+".sha256"}]}

class RepoRenameCompatibilityTests(unittest.TestCase):
    def test_canonical_repo_ids_are_used_in_live_update_clients(self):
        self.assertEqual(orbit_cli.REPO,REPOSITORY)
        self.assertEqual(orbit_updates.REPO,REPOSITORY)
        self.assertEqual(orbit_cli.RELEASE_ARCHIVE_URL,
                         "https://github.com/"+REPOSITORY+"/releases")
        self.assertEqual(orbit_updates.RELEASES,
                         "https://api.github.com/repos/"+REPOSITORY+"/releases?per_page=100")

    def test_candidate_metadata_and_cli_links_do_not_rely_on_redirects(self):
        with patch.object(orbit_cli,"download",return_value=json.dumps([release()]).encode()):
            latest=orbit_cli.latest("candidate")
        self.assertEqual(latest["version"],"0.27.0")
        self.assertEqual(latest["url"],"https://github.com/"+REPOSITORY+"/releases/tag/v0.27.0")
        self.assertTrue(latest["zip"].startswith("https://github.com/"+REPOSITORY+"/releases/download/"))
        self.assertNotIn(OLD_REPOSITORY,repr(latest))
        live=orbit_updates._newest([release()],"candidate")
        self.assertEqual(live["url"],latest["url"])
        self.assertNotIn(OLD_REPOSITORY,repr(live))

    def test_no_legacy_repo_slug_in_active_code_or_current_docs(self):
        active=["orbit_cli.py","source/runtime/orbit_updates.py",
                "scripts/prune_merged_branches.py","scripts/check_release_readiness.py",
                "README.md","docs/RELEASE-QUICKSTART.md","docs/RELEASE-PROCESS.md"]
        for rel in active:
            with self.subTest(file=rel):
                content=(ROOT/rel).read_text(encoding="utf-8")
                self.assertNotIn(OLD_REPOSITORY,content)

    def test_legacy_mcp_server_and_extension_identifiers_are_preserved(self):
        self.assertEqual(installer.SERVER,"orbit-core-native")
        self.assertEqual(orbit_mcp.VERSION,"0.28.0")
        self.assertIn("orbit-core-mcp",(ROOT/"scripts/build_antigravity_plugin.py").read_text(encoding="utf-8"))
        self.assertIn("orbit-core-mcp",(ROOT/"scripts/build_plugin_suite.py").read_text(encoding="utf-8"))

    def test_version_matches_without_rewriting_future_roadmap(self):
        self.assertEqual((ROOT/"VERSION").read_text(encoding="utf-8").strip(),"0.28.0")
        self.assertEqual(installer.VERSION,"0.28.0")
        self.assertEqual((ROOT/"NEXT_VERSION").read_text(encoding="utf-8").strip(),"0.29.0")

if __name__=="__main__":
    unittest.main()
