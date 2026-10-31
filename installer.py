"""Orbit Universal local project setup (see VERSION).

No agent CLI is spawned. No project code or Git is modified. Local MCP uses
Python stdio; file/config edits are previewed and require explicit confirmation.
"""
from __future__ import annotations
import argparse
import json
import hashlib
import os
import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent
VERSION = '0.28.0'
SERVER = "orbit-core-native"
HOSTS = ("antigravity", "codex", "claude-code", "vscode")
SCOPES = ("machine", "project")
# Hashes of exact vendor-packed v0.22.0 stock files ONLY: safe upgrade after backup.
OLD_STOCK_SHA256 = {
    '183dd19ed5f35ea4bc7c4e01e1c57274ed062203fbed8a7815608bb6de9dbfaa',  # pre-portability source/runtime/orbit_mcp.py
    '67ee9124509c2ac854a22649dbb5c690ee69f78f79754f7e06377336f34029e6',  # pre-portability source/runtime/orbit_tasks.py
    # Source-verified intermediate official agent templates, commit 7e1372f.
    # Includes Windows line endings and Claude conversion; owner edits still block.
    'e5bed463ed9e7b9198edeca1d1c15b1ecc36fcdcb69cf465d25bed3334d45869',  # orbit-architect.md, native, LF
    '07c77ce4769eff768b5a7be898efc0544af074ebd070df1d192fad597a1df91c',  # orbit-architect.md, native, CRLF
    'a0e4f671eef0c7db9dcd9bf94bd496cae9cda9840484690762831efaf76f415f',  # orbit-architect.md, Claude Code, LF
    'db10fef153d7dbce79476c596f5828d8dc99d852751cef7eea9e0ac8f11e067d',  # orbit-architect.md, Claude Code, CRLF
    'd9966db5e4f7dc852dc55d443c6c3b620a232f18342ad603884bfa3336ca00ce',  # orbit-backend.md, native, CRLF
    '8a29356c671eeedd3ec1e49c1136fae5c74b80c09a7f36dfe4011e10c64556ba',  # orbit-backend.md, Claude Code, LF
    '72b8d26456da95426847e6927352aab43f5c02679b5d9b3b5504a93b320ceaa9',  # orbit-backend.md, Claude Code, CRLF
    '1f9191748666736860be0ba048f1b3bff0be0c17874dc023f7eefcbcaf2f5feb',  # orbit-data.md, native, CRLF
    'e6b563e700e9e30f30c5b9455a4ce21d457405a993b682c581f69932927928d6',  # orbit-data.md, Claude Code, LF
    'd5b48c7bb144a812502604877f450b665082fa436ddc9e559cdf50364734583f',  # orbit-data.md, Claude Code, CRLF
    '927eae2317e938acb9b59c50db4db949d01dcd93d9171e22a5922091addc37a0',  # orbit-devops.md, native, CRLF
    '87db755c0021ef3f8e174cd6dcb52cdca962064ae83a3c28cf367f6269dc4c9d',  # orbit-devops.md, Claude Code, LF
    '0070d6cf0fb00cd6dd8dea4168597accbe5d17e85d4a26f55e769b2c618f2871',  # orbit-devops.md, Claude Code, CRLF
    '8f073c7d1535b3e607841ff7eff27f52606073ceab93cd269acc5c1cd26fd2ee',  # orbit-frontend.md, native, CRLF
    '2bb51d5063ee45dfc3897f2377fe82ea6adebaa5b1e8fc50f98a0ae1609cca9c',  # orbit-frontend.md, Claude Code, LF
    '95c9ec95e140cef921e7837441a3f2f3c4645f5741981087437047bf8020190e',  # orbit-frontend.md, Claude Code, CRLF
    '2b143e276dade0c48f19c4696e6c301bb65f2da04c689bb12e798132408cde32',  # orbit-integrator.md, native, CRLF
    'c9176f7118ce5f60c40cfad902839ae3e981d1f26ea3fe5e08e6cdf51f556cf1',  # orbit-integrator.md, Claude Code, LF
    'e2ffa8c26cbb2ad0f6da2db74ad00602ea091bd44dc12e5df5bd324ce5271b8c',  # orbit-integrator.md, Claude Code, CRLF
    '2fe2de371093caa3fa53237afeb4fad0ff9a338438f88d3517874d5bde69bce9',  # orbit-qa.md, native, CRLF
    'e875388d8c87772d0f2a5227417fe02ebc5a7cf53db9662c382a276434912eda',  # orbit-qa.md, Claude Code, LF
    'ff6e2f5c777fd3aaf1c41324032bdd07bc6fa75d789b82f560f16407130aabab',  # orbit-qa.md, Claude Code, CRLF
    'cab6faa188086fd592de4c2c4d90232ce67ebb643e5f2016592605c14f62c3c9',  # orbit-research.md, native, CRLF
    '23c9cd5e7382fe78ebd547448afa4b5415c02c212e597ce4f00b85dbb8c86814',  # orbit-research.md, Claude Code, LF
    '685a7a1c0d3787711bad86a83d3d7efef184dc72976f1969a406c91c50762ba6',  # orbit-research.md, Claude Code, CRLF
    'e7c21456a057fb1400c1afa1e1d364931043db28ac9d50a6f5a74d0b7b209ec2',  # orbit-reviewer.md, native, CRLF
    '20ac2c8969c897aec4880183280e68e12bf49045b8d647d4af91df23b2f6f963',  # orbit-reviewer.md, Claude Code, LF
    '9d922eeffb0d296990162ca958953f952d590578c46e3b5948aed92ecea81195',  # orbit-reviewer.md, Claude Code, CRLF
    '01bdf9a23493be364d4e1b6d9c6268cad4dd8bf41347de7737aefe05ae34c3e0',  # orbit-security.md, native, CRLF
    'ccf467cfb29238a4b11845b9c2c7bb6db14ea8c9bb7d51c0f11d36b5e44b278e',  # orbit-security.md, Claude Code, LF
    '06d93020ade5e7ca381cf4859e08f6a20c8ce305bb486647bcd8d6d18cee2bbf',  # orbit-security.md, Claude Code, CRLF
    'da068886b64b59be374d6378487ff1814613b4b7a7e437103fac2d9725cc700c',  # orbit-ux.md, native, CRLF
    'a959c702daa1be2db7063adc5da2a4eb471998b4245623d18825f6dfbd31ce83',  # orbit-ux.md, Claude Code, LF
    'a4eda89055c9972dca0ff3429bf7f775a8baf0220759ab9d1acfb6cb43ec576f',  # orbit-ux.md, Claude Code, CRLF
    'e44743a5fcbfa795e3c3ec6a0fb8c355ab045de8c0a0619bb2292fdf2dfbc966',  # orbit-writer.md, native, LF
    '709bec90b7fcafe7ad0a2e42a2ac966e50a1d2276626ea6ac01cf98160e46226',  # orbit-writer.md, native, CRLF
    '14155bf1bbd96e3d51575efe3143ced9ab0a0b5f96c558b30cac03a6491e4e27',  # orbit-writer.md, Claude Code, LF
    '409c92b3d6f452d0e38e7df312042832bf0c63fb4d8f3cfc1510600345a359d1',  # orbit-writer.md, Claude Code, CRLF
    '65e2798b9f38770a6f9fe5cef336ceefe04b052e02d5536fdd22379385f00fac',  # orbit.md, native, LF
    '446ffe8ed57d06dd8f2ca8186567c8aae65f375a52a56f0762a4c814b88e8486',  # orbit.md, native, CRLF
    'd8ce7b0d85364a7dab39e642b64ceb2571d4c42865b3f9a2d46b55cd0e89574d',  # orbit.md, Claude Code, LF
    'fa7b276fbc47da9fcabdf4d079a3e2dba4c1e6fd55816d463a2d97978f757998',  # orbit.md, Claude Code, CRLF
    # Exact source-verified stock files produced by the immutable v0.24.1
    # tag installer. Calculated in an isolated prior-tag installation on CI.
    # Only byte-for-byte matches qualify for backup-first upgrade; any edit
    # by the owner still triggers manual review rather than being overwritten.
    'fe05b82d899ef63d9cf79b9c8fae20cd70d7cb1b850f7fe68503a0f4fc899db7',  # orbit_cli.py
    '25a4370768eda1397c3562431d51dbf402ee1d1e8f5461ebc667260bc0c70427',  # installed orbit/SKILL.md
    '83465a5f4a9fbcf99bff5739f9864cb38ce336e9455d4f2b1465e65c7e8820ef',  # COMPONENT-REUSE.md
    '2f81e2dcb796a3eb432464a51eb245a068f9e5bc245d7ce2e8379de093c3d802',  # DECISION-ROUTING.md
    'a9563ac5429776eef9bd5707156c677e60a4be1ae6a58bc923f32253f9753eb6',  # DOCS-AND-CONTEXT.md
    '240c938ea40da8126a56e4adceb59ff5081b4560fdd10a2b9e63ac1aed564d43',  # PRODUCT-KIT-ADOPTION.md
    '2c1436556ab6450f23a85067daf05b1c10850d7ec2e9a4045de81594e8569dd0',  # PROJECT-INTAKE.md
    # Exact unmodified project-host stock files emitted by the immutable
    # published v0.25.1 tag installer in the disposable CI upgrade fixture.
    # These are SHA256s of installed files, NOT a permission to overwrite edits.
    # Retain existing backup-first review and refuse unknown/customized bytes.
    '8964fcc25fdf2bd4febee41d2d6d9b5b6536245264daef9b0678956d252a1f54',  # v0.25.1 orbit_cli.py
    '56b0aac2f4e092d5425c3eb6594c2ebc184442ffce63050fd327e9bd0350abd9',  # v0.25.1 installed SKILL.md
    '2ba28070239300b080994879a8df81996172df90c5910ad346c76114252fd2ff',  # v0.25.1 HANDOFF.md
    'b45ad9da0a259838c16a84ed8f4f3440973761e9bc1174e82527d10206d8c418',  # v0.25.1 PROJECT-INTAKE.md
    'ab5dd7d29724a966f80dbc0c540be6c3e7042671959d5d85e266d8b480d98829',  # v0.25.1 TASK-LIFECYCLE.md
    # Exact official v0.26.0 stock TASK-LIFECYCLE.md (verified from immutable
    # published v0.26.0 tag). Modified files still trigger manual review.
    'f8d5293d2869f01008b4126b80d1c0e2a11e049fe72019daa51624864343876a',  # v0.26.0 installed TASK-LIFECYCLE.md
    # Previous official Edge/Chrome QA candidate (c027e73) stock files.
    # Exact SHA256 only; unknown/customized content remains protected.
    '8fb102a9b367332ef92d9f1204e69996f6ef1bee033354dd1971735ccd46ba1a',  # source/runtime/orbit_mcp.py
    '56b544b943add6fe3a321ed74f694de0059b35a1fe1a497195d81560b6a7b31f',  # source/runtime/orbit_browser.py
    '5310720aa06c6d44a4cd18065f2b6da74b1284e4478f12e7be7a5aba1679276f',  # source/runtime/orbit_build.py
    '88ac4083b7fea0739355812f9f8c0d83c0e24591c23a96fdec025f8521c508a6',  # source/skills/orbit/references/HANDOFF.md
    'de6db388c651f35cb4f93db887e7f27b5453ea37e0184a1717a933e1f40b560c',  # source/skills/orbit/references/TASK-LIFECYCLE.md
    # Recognized previous unmodified v0.24 files; upgrade after backup, never overwrite owner edits.
    'f6a4bd3c1e21d936403954b273d7e882dc897211e2da471ec8360e6639ee45a1',
    '0f929f83c43c11b46a666387dd3d7581e081876a4cf401e2f2928b1a3f97f85c',
    # Exact previous v0.24.0 stock files for optional agent-browser support upgrades.
    '0f929f83c43c11b46a666387dd3d7581e081876a4cf401e2f2928b1a3f97f85c',
    '81bcd52a57163a9b071212a02ca9421a4df832ef6cfbaee9ff62dc46dc19aaa1',
    # Exact previously distributed v0.24.0 test candidate used in the user's
    # Windows installation. Only these immutable hashes are eligible for an
    # automatic backed-up replacement. Customized files still halt setup.
    '1e384ca291c3fe20cc2a866f103abbc3139c1c5feffc250c3e6999975dc3754a',  # orbit_browser.py
    '508186df8c690bb3c64b147a5163399e42824ac251543a82f5482c427331171a',  # orbit_mcp.py
    # Exact official 0.24 candidate files for backed-up in-place upgrade.
    '17378035a0ced4e4f8589875ff69df8ae2d83b228f3b8c41674f027c9ab183db',
    '5e738a0eafc8e3c553f3f85815c41d573d39bfab5dd4977f3eeb9722393b2b96',
    '526a73c0441248c44a1355d59311bf2e0adfb3312152fe0357ea12e80bb4d063',
    '7290549872effa8d2cf533b7bd5ba6e34a1d7eb710afd3f7d8f1c28ff3bda267',
    'c2c9c7a9d93f6d3788ebf309ad67054d75f82c5d67e9c65e016a207f0a31e482',
    '75c22c8fc6100605940b210eab5d3e0f23006db5c0baeb41566f08c6ff659992',
    '5b2ec9bbbfd3fc5910c6bc2648b670e4a91c131c2f32df7c6fe67614ffa90095',
    '670b6b91414af8ce40c9f521d487776daef2d92a4dcaa461b55d8b1e7f35658f',

    '36b2fda1614b658e7f15e3c80c63e50f6727e2b3f013e6b2d7ee30fb2768d6fd',
    '063ff538079f946bfba162f610f5d10728485c77d6d8126cabaa95c8dfa98822',
    '096c989e51db5c0f123aee197e3c65456a0e5508ec7902a50ce8a5cb3aefc17e',
    '0ff44846a5d26607bbed8d1d3f506e898546e13a614b76962c6029a02e195c44',
    '10fa370a50e8cdc3032c40f5ddec3e221c2999656a7158f5585b053c0dbd67c9',
    '17378035a0ced4e4f8589875ff69df8ae2d83b228f3b8c41674f027c9ab183db',
    '23c88ebcac418d20857737265a900c30c18851bfd0ef4fd27f77f76f6eb59439',
    '291f371c54a393ca37ed90b60a043dd7b61aae1c41ccbcc14624954c2c12f812',
    '2f47b90bc026ee0da72facd7781b6730246986b69226df7b4908493f4c3c4ca3',
    '3413d2f2571460657a1e90ee714e2d4ac8b9223bc0d6c255d2e9e4c9ed57002d',
    '3705b983148983d3d35a9b4dbd53c9cf704a3e445143f79842145a663062ca2f',
    '38662fc36fd3a48d698fcd2039e10a2c6dfb304b0b4050a707237faf033ffe30',
    '38e3094ab64cda3a81ff6d9d84c4dde26620e80f371e84a9fec82c25dcb8cc2d',
    '39ecb53621d44bf4e573cff5362b04250a1d3100f65d62c3ecb1c4573c9fcf23',
    '3c6965f344fd4e8536391f97ef7388c51ce6e3dd385498b467ebe43e8245ee79',
    '408f244154cd9886f838e8c288e4d4e60ac82327c066263c2edb88400e1cc6f0',
    '4433fbbb27920a5a89e3c27a130bc3f921775687cafbdea5009f27181ef0bfc5',
    '4710a7fa63678f3d8a75e68e49ac3e9142895d21e4b7624612d082f0d857663b',
    '4b0b06086e34eb3769fd09fcf05cb3a3d133ee2b3859822f3b26dc62aea702ef',
    '4e439caf19e4fffa036b60c13c346f7a6199cf20b5929948631286c6a5839a3e',
    '5269a660c24014f3978d876193e56caa404496ac00701a3197b3616bd818a9b3',
    '56337132ae0887cb30eae7c0755563645fab1580e23119ad0ca7861d74893bac',
    '5686839ccddc37932d98a68cd79fe7b673a86183ac6bea93d0e92a47e0bef55e',
    '6adbe3688181d077fc33f04800b13e334ecb49a0a7450dc91b741ce2a61122b9',
    '6c4d8d33a7503ffc18fa22460b9964af1a559c2a192e5090afeee57a58eb339a',
    '6d96b9f10655a1e8e711850f5403a7add8a8257d4f3bb5ba1f215b82b07f8099',
    '7db286c05dcd8bd77a4585f2ad387c04107aff132d84f394faa4ed6bfaf88314',
    '81bcd52a57163a9b071212a02ca9421a4df832ef6cfbaee9ff62dc46dc19aaa1',
    '85a3599bc5c43dfdb22f14cf9b73655417292c6f4fe91961c9fe051b27f0c604',
    '86e14167e128f639fdbe8652607cf52e30bede136fbf556a20236b769421ed89',
    '90b965281ac32b4ae86233fb8d555cccf3dcb424ca0e7123bf5cdf45f008c370',
    '95906cb1cda92139f4154303f319a0fbd489dd15d720edad3dd0fcf28591189f',
    '99ee594c18af3e5a03209c395b59fa4573a9c75c42eb0a7ae9eff3e9c6cbdbf5',
    'a3661107a54f45efdb4c5c24364e9e5939c2e42c49be91695675473a33b256aa',
    'a9db9aeeb44bef29a1d18918762b4155dbc9d5c2aee02b2a8561f9759e15ac02',
    'ac3c4581f27583552db2a74ed15622475ec0c384718b11888b1866dd98d3cd37',
    'bdcdfa4f608ffdecc96be6fa03c2950836060f530a39605dfbd59f9140b31e4b',
    'c6664ae0e2e9d697ff2946b176a6e0b2e9c5b05c78e185117ddc997fd5803714',
    'cbecb60f81d240f4941a329858e67bdb9ca17b2107134a430a486d1020e82911',
    'ccb45ee7d77d780b2393011425acf4f9b7df4d92bb3ce4a7cce9ee600c26cf49',
    'd258c8983def9b969d5a1ecaa6e02572f31ad9a3815c9d683170bf6455ce9443',
    'd691d0b30b5cc6fd40557f31de46c5c1963eff698dba630812f9a76a03f04c35',
    'de6e74a86bb3d7cd5909aa9143a11b3b57680e48360f7400d1deef60bdd6d075',
    'dec31c1a6657466fc11269e75f880bc09e65a9bd2b4a5b382c602387d2a063f3',
    'e5fb9af237998b0691a88309f902f9d49ba36e1080746b489c23ed3848b68c70',
    'ea012d2f45049bc7d3433c775da6aaff46955a1ff0827e4f311f120bde204d3f',
    'eac64b2c255bdcae6ee64d41708f3adf21d4b7b0623cd5ddb0c1281a2f148071',
    'eb98bde2a77696dbcdd9541f890ae5993017de4bab42acb979e1948c46ccbfc0',
    'f151a221c0a282a2a79cc3dcbfffe75aa9dbb635e3c7195c03bfdb025c41ca47',
    'f19689b6d352ef5a34f165a99c8b4ac624a279e7c39ef5b3cb33f92122888b03',
}



class SetupError(Exception): pass


def python_binary() -> str:
    p = Path(sys.executable).resolve()
    if os.name == 'nt' and p.name.lower() == 'pythonw.exe':
        p = p.with_name('python.exe')
    if not p.is_file(): raise SetupError('Python interpreter not found')
    return str(p)


def user_home() -> Path:
    # Override only useful for isolated test environments; standard install uses OS home.
    return Path(os.getenv('ORBIT_SETUP_HOME') or Path.home()).expanduser().resolve()


def runtime_folder() -> Path:
    base = os.getenv('ORBIT_UNIVERSAL_HOME')
    return (Path(base).expanduser().resolve() if base else user_home() / '.orbit-universal') / VERSION


def check_project(p: str | Path) -> Path:
    raw = Path(p).expanduser()
    if not raw.is_absolute() or raw.is_symlink():
        raise SetupError('Select an existing absolute, non-symlink project directory')
    root = raw.resolve(strict=True)
    if not root.is_dir() or root == Path(root.anchor) or root == Path.home().resolve():
        raise SetupError('Select a specific project, not home or the drive root')
    return root


def check_dest(path: Path, root: Path) -> None:
    if root not in path.parents and path != root:
        raise SetupError('Refusing to write outside project root')
    for x in [path,*path.parents]:
        if x == root: break
        if x.is_symlink(): raise SetupError(f'Symlink destination is not allowed: {x}')


def toml_str(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)


def agent_claude(content: str) -> str:
    m = re.match(r'\A---\s*\n(.*?)\n---\s*\n(.*)',content,re.S)
    if not m: raise SetupError('Agent YAML header missing')
    f, body=m.group(1),m.group(2)
    name=re.search(r'^name:\s*(\S.*)$',f,re.M)
    desc=re.search(r'^description:\s*(\S.*)$',f,re.M)
    if not name or not desc: raise SetupError('Agent name/description missing')
    n=name.group(1).strip().strip('"\'')
    d=desc.group(1).strip().strip('"\'')
    if not re.fullmatch(r'[a-z][a-z0-9-]{1,70}',n):raise SetupError('Invalid agent ID: '+n)
    return '---\nname: '+n+'\ndescription: '+json.dumps(d)+'\n---\n'+body


ORBIT_SKILL = '''---
name: orbit
description: Coordinate a software project through Orbit: inspect project, plan milestones, use authorized specialist subagents, report evidence, and save bounded SQLite project state via Orbit MCP. Use for new apps, debugging, review, handoffs and resume.
---
# ORBIT — universal host adapter

You are the lead project orchestrator, using this host's current model and native tools. The Orbit MCP is a task/memory service; it does NOT spawn models or execute app code. Respect the host's permissions, sandbox and user approvals.

For new platform, stack and UI decisions offer recommended answer **or Custom / type own words**, then record exact user wording with orbit_intake_answer and ask only necessary conditional followups. Use orbit_decision_route to compare existing platform components, audited prebuilt libraries or custom design for the actual product type and accepted stack. Use orbit_model_route with real host-reported model names before significant delegated roles when supported; this MCP does not change models, install skills, spend quota or verify entitlements. New type-specific workflows skip irrelevant browser-only checks for native apps, SDKs and OS platforms. Load references/DECISION-ROUTING.md only on a relevant decision.

On each resume call orbit_project_resume once and read recovery.status/next/pending_tasks. If its `update_notice.status` is `UPDATE_AVAILABLE`, show the published version and offer Update / Later using real host-supported controls, or plain text when controls are unavailable. `orbit_update_status(refresh=true)` only checks public release metadata, never installs. To actually update, the user launches the stable local `orbit manager` GUI, selects host/project scope and approves Install update. Never use an MCP model argument as proof of host consent; no auto-download or auto-apply on resume. The local updater needs a host restart to load a new version. If multiple active builds exist ask which one; never guess or restart old stages. Use the existing orbit_project_checkpoint for doing/next/blockers. For substantial research or QA load references/PRODUCT-KIT-ADOPTION.md as needed; apply smallest complete change and two-unchanged-failures stop. Do not read all project docs every turn, run detached Product Kit agents, or auto-push Git.

**Orbit is the product, not the demo app.** In a fresh product, offer Scope first or user-delegated sensible defaults; ask the highest-impact question and adapt the next question to the user's last answer. Begin RESEARCH only after accepted intake, then show an editable, task-based PLAN for approval before IMPLEMENT. New build PLAN passes only with evidence containing title, summary, tasks, approval_method and an actual user approval/delegation reference (caller-reported). Existing build stage records stay valid. Show real task-ledger progress and next step; do not claim a new visual builder UI in an MCP host.

**Fast, selective context:** read the small project brief/checkpoint, relevant latest decisions and only the reference/source files needed for this request. Do not load every Orbit instruction/reference/ADR or regenerate the full plan on each turn. Deeper research is for material new requirements, unfamiliar dependencies and high-risk architectural/security changes; trivial changes need targeted code inspection and tests. Skills are optional, checked for availability/permissions, never automatically installed.

1. Confirm the selected project folder and stable project key. Before planning, inspect current Git status and existing docs/source. Do not invent an existing implementation. **For new nontrivial products**, load `references/PROJECT-INTAKE.md`: interpret everyday prompts, propose project category, complexity and maturity, ask one highest-impact question first, record each choice with orbit_intake_answer, branch with orbit_intake_followup when prior answers justify it (normally 2-5 total), and offer **Use recommendations**; await choices unless user explicitly authorizes defaults. Skip repeat interviews for established/resumed projects.
2. Call `orbit_project_resume` or `orbit_memory_recall` on `orbit-core-native` when connected; if disconnected, say memory is unavailable, never claim persistence.
3. **Before** building the plan, load `references/DOCS-AND-CONTEXT.md`. Audit owner docs and ADRs by purpose; establish approved compact `.orbit/PROJECT.md` index only when appropriate; ask actual architect/writer agents to create needed short vision, architecture, roadmap, design, requirements, API and project-type docs, or write them sequentially with the host if agents are unavailable. Never duplicate/overwrite user docs. Then plan product, UI, backend/API/data, security, tests, CI, release/rollback as actually applicable.
4. Refine the agreed plain-language goal with the **current host model** into a faithful 120–220 word brief and canonical file links; future tasks consume brief, checkpoint, 0–3 relevant memories and file deltas rather than entire transcripts. Prefer existing docs and components; write needed verified drafts only and preserve all owner documents/ADRs.
5. For specialist tasks: use `orbit_task_plan`, then reserve using `orbit_task_reserve` **only** for user-authorized host delegation. Use this host's native subagent interface (Antigravity `invoke_subagent`, Codex delegation, Claude Code Task/Agent tools) only if actually available. Do not call another provider's CLI. Parallelize only non-overlapping work; default 2 task reservations.
6. After a successful native start, record the real session using `orbit_task_started`. Do not claim an agent is running merely because a task was reserved. Report outcome with `orbit_task_report` and independently review actual diffs/tests with `orbit_task_review`. Reject scope violations, failed tests and unverifiable results.
7. Use `orbit_project_checkpoint` with the fresh revision and user-approved `confirm_write=true` after meaningful work. Protect existing `.orbit/STATE.md` and use the same project key across hosts.
8. No automatic git add/commit, push, merge, deploy, delete, billing or auth changes. Never expose secrets. If an operation is unavailable or blocked, report accurately.

Before coding, analyze product-specific invariants and edge cases, scan existing code and capability inventory and decide whether to reuse a trusted built-in library, a reviewed maintained prebuilt dependency or small justified custom code. Vercel Labs agent-browser is an optional QA provider, not a product UI framework; never silently install it. Document the dependency tradeoff. Before delegating to a specialist, call `orbit_capability_select` with the real project path, task objective and host tools. Review installed skill compatibility/provenance. Prefer existing trusted skills and native host tools; if something is missing, research using the host's approved web search. The official Impeccable frontend design skill (https://impeccable.style/) is an optional candidate, never silently installed or treated as universally best. For browser QA, optional Vercel Labs agent-browser (https://github.com/vercel-labs/agent-browser) exposes its own MCP; Orbit may select it only when the host has actually connected its tools, with separate permission to install/connect. Do not treat configured MCP entries as connected, and do not let agent-browser reports bypass the Orbit-recorded Playwright BROWSER_QA gate. Third-party installation and adding MCP connections are user/host approval-gated. Review source/permissions first, then verify actual availability after approval. Specialists may recommend, not self-authorize or spawn more agents.



## Local app previews (v0.24 candidate)

Once implementation has been approved, invoke `orbit_preview_start` first without `confirm_run` to inspect the exact argv and loopback URL. Only call it with `confirm_run=true` after user/host permission for running the project code. Use `orbit_preview_status` to verify local HTTP readiness and inspect bounded logs; use `orbit_preview_stop` with `confirm_stop=true` before finishing when applicable. Each run is a local-only server: do not tunnel, deploy, expose public ports, or claim browser/visual tests ran unless the host browser or Playwright truly executed. Preview process control remains active-session-only; after an MCP restart, the build stage resumes from SQLite but OS preview processes need manual cleanup.

For app-building, create or resume a durable run using `orbit_build_begin` / `orbit_build_status` before task delegation. Record objective and advance PLAN, IMPLEMENT, PREVIEW, BROWSER_QA, REVIEW and CHECKPOINT via revision-guarded `orbit_build_advance`. Only report PLAN/IMPLEMENT as caller-reported evidence. PREVIEW requires a ready Orbit-managed local server. BROWSER_QA requires an actual recorded interactive pass from `orbit_browser_qa` after explicit approval; it produces a private screenshot and bounded console errors using installed Playwright Chromium. If Python Playwright is unavailable, an explicitly connected agent-browser MCP can provide supplemental host-controlled snapshots, real interactions and screenshots, but Orbit's existing gate still requires a passing Orbit-recorded Playwright run. Keep the gate on HOLD until supported attestation is implemented; never manufacture a pass. CHECKPOINT requires real `.orbit/STATE.md`. The host owns the iterative build/repair loop; MCP tools do not independently decide, generate, or run agents.

For a Todo Lab test, develop the app through milestones and explicitly report native delegation and MCP calls separately. A generated test report is not proof that a test ran: show command and exit code.
'''

ORBIT_LEAD_CLAUDE = '''---
name: orbit-lead
description: Lead software project orchestrator. Inspect code and docs, coordinate scoped specialist agents, verify tests and checkpoints. Use for project planning, development and resumptions.
---
You are Orbit, the main orchestrator. Follow `.claude/skills/orbit/SKILL.md`. Do not create competing project documentation or spawn external agent CLIs. Use host-native subagents only where available and authorized, and the local Orbit MCP for SQLite memory and task ledger. Never claim a tool ran without its result.
'''

AGENTS_GUIDE = '''# ORBIT project guidance

This project uses the repository skill `.agents/skills/orbit/SKILL.md`. When asked to work as Orbit, invoke `$orbit` or read that skill, then use connected `orbit-core-native` MCP tools for checkpoints, task ledger and memory. The model and native subagent executor belong to the active host (Codex, Antigravity or Claude Code), not MCP. Do not invoke a separate AI CLI; use approved native delegation. Verify outputs; do not invent test runs or saved state. Never stage/commit/merge/deploy without authorization.
'''

CLAUDE_GUIDE = '''# ORBIT project guidance

For Orbit workflows load `.claude/skills/orbit/SKILL.md`. Choose `orbit-lead` as lead when appropriate; delegate frontend/backend/QA work using Claude Code's native agents when supported. Use the connected `orbit-core-native` MCP tools for local persistent memory and ledger. Do not invoke external model CLIs or modify unrelated projects. Validate evidence before accepting work.
'''


@dataclass
class Change:
    target: Path
    data: bytes
    action: str
    description: str


def same_or_create(changes: list[Change], dest: Path, data: bytes, root: Path|None, desc: str):
    if root: check_dest(dest,root)
    if dest.exists():
        if not dest.is_file() or dest.is_symlink():raise SetupError('Destination exists and is not a regular file: '+str(dest))
        current=dest.read_bytes()
        if current != data:
            oldhash=hashlib.sha256(current).hexdigest()
            if oldhash in OLD_STOCK_SHA256:
                changes.append(Change(dest,data,'UPGRADE',desc+' (recognized stock file; backup made)'))
            elif dest.name in {'AGENTS.md','CLAUDE.md'}:
                # Existing owner guidance is authoritative; Orbit's skill remains available.
                changes.append(Change(dest,current,'PRESERVE','Existing owner guidance retained'))
            else:
                raise SetupError('Existing file differs from recognized Orbit versions; no overwrite.\n\nReview this file (it may be customized or from an unrecognized build):\n'+str(dest))
        else:
            changes.append(Change(dest,data,'SKIP',desc))
    else:
        changes.append(Change(dest,data,'CREATE',desc))


def stock_runtime_path(prior_path, next_path):
    """Validate an existing versioned Orbit runtime without trusting foreign paths."""
    try:
        prior=Path(prior_path).expanduser()
        target=Path(next_path).expanduser()
        return (prior.name=='orbit_mcp.py' and target.name=='orbit_mcp.py'
                and re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+',prior.parent.name) is not None
                and re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+',target.parent.name) is not None
                and prior.parent.parent.resolve()==target.parent.parent.resolve()
                and prior.is_file() and not prior.is_symlink() and not prior.parent.is_symlink())
    except (OSError,ValueError):
        return False


def merge_json(changes: list[Change], dest: Path, entry: dict, root: Path, desc: str):
    check_dest(dest,root)
    old={}
    if dest.exists():
        if dest.is_symlink() or not dest.is_file():raise SetupError('Unsafe config: '+str(dest))
        try: old=json.loads(dest.read_text(encoding='utf-8'))
        except Exception as e: raise SetupError('Cannot parse existing config: '+str(dest)) from e
        if not isinstance(old,dict): raise SetupError('Config must be object: '+str(dest))
    servers=old.get('mcpServers',{})
    if not isinstance(servers,dict): raise SetupError('mcpServers must be object')
    if SERVER in servers and servers[SERVER]!=entry:
        prior=servers[SERVER]
        # Only migrate the exact previous stock server command shape, preserving other MCPs.
        if not (isinstance(prior,dict) and prior.get('command')==entry['command']
                and isinstance(prior.get('args'),list) and len(prior['args'])==1
                and stock_runtime_path(prior['args'][0],entry['args'][0])
                and set(prior)==set(entry)):
            raise SetupError('Existing Orbit MCP registration differs; no overwrite: '+str(dest))
    obj={**old, 'mcpServers':{**servers,SERVER:entry}}
    body=(json.dumps(obj,ensure_ascii=False,indent=2)+'\n').encode()
    if dest.exists() and json.loads(dest.read_text())==obj:
        changes.append(Change(dest,dest.read_bytes(),'SKIP',desc))
    else:
        changes.append(Change(dest,body,'CREATE' if not dest.exists() else 'MERGE',desc))


def stock_codex_body(body,python_cmd,runtime):
    """Accept only an exact existing stock TOML definition; reject custom fields."""
    matched=re.fullmatch(r'(?ms)\s*command\s*=\s*("(?:\\\\.|[^"\\\\])*")\s*\nargs\s*=\s*\[\s*("(?:\\\\.|[^"\\\\])*")\s*\]\s*',body)
    if not matched:return False
    try:
        return (json.loads(matched.group(1))==python_cmd and
                stock_runtime_path(json.loads(matched.group(2)),str(runtime)))
    except ValueError:
        return False


def merge_toml(changes: list[Change], dest: Path, python_cmd: str, runtime: Path, root: Path):
    check_dest(dest,root)
    old = dest.read_text('utf-8') if dest.exists() else ''
    section='\n[mcp_servers."orbit-core-native"]\ncommand = '+toml_str(python_cmd)+'\nargs = ['+toml_str(str(runtime))+']\n'
    matching = re.search(r'(?m)^\s*\[mcp_servers[.]["\']?orbit-core-native["\']?\]',old)
    if matching:
        if section.strip() in old:
            changes.append(Change(dest,old.encode('utf-8'),'SKIP','Codex Orbit MCP already matches'))
            return
        # Migrate only a known stock Orbit config section from v0.22; preserve surrounding TOML.
        match=re.search(r'(?ms)^\s*\[mcp_servers\.["\']orbit-core-native["\']\]\n(.*?)(?=^\s*\[|\Z)', old)
        if match:
            body=match.group(1)
            if stock_codex_body(body,python_cmd,runtime):
                next_body=old[:match.start()]+'\n'+section.strip()+'\n'+old[match.end():]
                changes.append(Change(dest,next_body.encode('utf-8'),'APPEND','Codex migrate stock MCP with backup'))
                return
        raise SetupError('Codex Orbit MCP table already exists and differs; review manually: '+str(dest))
    body=(old.rstrip()+ '\n'+ section if old.strip() else section.lstrip()).encode('utf-8')
    changes.append(Change(dest,body,'CREATE' if not dest.exists() else 'APPEND', 'Codex project-local MCP table'))


def plan(project: str|Path|None=None, hosts=HOSTS, scope='project') -> list[Change]:
    if scope not in SCOPES: raise SetupError('Select machine or project install scope')
    root=check_project(project) if scope=='project' else None
    home=user_home()
    hosts=set(hosts)
    if not hosts or hosts-set(HOSTS):raise SetupError('Choose supported host(s): '+', '.join(HOSTS))
    src=PACKAGE/'source'
    runtime=runtime_folder()
    if any(p.is_symlink() for p in [runtime,runtime.parent]):raise SetupError('Runtime directory is a symlink')
    changes=[]
    for name in ['orbit_mcp.py','orbit_tasks.py','orbit_capabilities.py','orbit_preview.py','orbit_browser.py','orbit_build.py','orbit_intake.py','orbit_decisions.py','orbit_updates.py','orbit_evidence.py','orbit_delegation.py','orbit_portable.py','orbit_swarm.py','orbit_swarm_draft.py','orbit_delivery.py','orbit_swarm_host.py','orbit_swarm_integrity.py','orbit_pulse.py']:
        p=src/'runtime'/name
        same_or_create(changes,runtime/name,p.read_bytes(),None,'Shared Orbit stdio MCP runtime')
    def add_references(dest: Path, boundary: Path) -> None:
        for ref in sorted((src/'skills/orbit/references').glob('*.md')):
            same_or_create(changes,dest/'references'/ref.name,ref.read_bytes(),boundary,
                           'Orbit guided workflow reference '+ref.name)
    # Stable installer-independent update launcher. Does not alter PATH automatically.
    same_or_create(changes,home/'.orbit-universal/orbit_cli.py',(PACKAGE/'orbit_cli.py').read_bytes(),None,'Orbit command-line updater and host detection')
    same_or_create(changes,home/'.orbit-universal/orbit_update_gui.py',(PACKAGE/'orbit_update_gui.py').read_bytes(),None,'Optional local update manager (no auto-install)')
    if os.name=='nt':
        launcher=home/'.orbit-universal/bin/orbit.cmd'
        body=b'@echo off\r\npy -3 "%~dp0..\\orbit_cli.py" %*\r\n'
    else:
        launcher=home/'.orbit-universal/bin/orbit'
        body=b'#!/bin/sh\nexec python3 "$(dirname "$0")/../orbit_cli.py" "$@"\n'
    same_or_create(changes,launcher,body,None,'Orbit stable update launcher; PATH modification is manual opt-in')
    # A persistent clickable manager launcher means future updates don't require
    # hunting for the original extracted setup ZIP.
    if os.name=='nt':
        manager_launcher=home/'.orbit-universal/bin/Orbit Update Manager.cmd'
        manager_body=b'@echo off\r\npy -3 "%~dp0..\\orbit_cli.py" manager\r\n'
    else:
        manager_launcher=home/'.orbit-universal/bin/orbit-manager'
        manager_body=b'#!/bin/sh\nexec python3 "$(dirname "$0")/../orbit_cli.py" manager\n'
    same_or_create(changes,manager_launcher,manager_body,None,
                   'Stable local Orbit Update Manager launcher; no PATH mutation')
    cmd=python_binary()
    script=runtime/'orbit_mcp.py'
    common={'command':cmd,'args':[str(script)]}
    if 'antigravity' in hosts:
        agents=(root/'.agents/agents') if root else (home/'.gemini/config/agents')
        skills=(root/'.agents/skills') if root else (home/'.gemini/config/skills')
        for p in (src/'agents').glob('*.md'):
            same_or_create(changes,agents/p.name,p.read_bytes(),root or home,'Native Antigravity agent '+p.stem)
        same_or_create(changes,skills/'orbit/SKILL.md',ORBIT_SKILL.encode(),root or home,'Antigravity Orbit skill')
        add_references(skills/'orbit',root or home)
        config=(root/'.agents/mcp_config.json') if root else (home/'.gemini/config/mcp_config.json')
        merge_json(changes,config,common,root or home,'Antigravity MCP configuration')
    if 'codex' in hosts:
        skill=(root/'.agents/skills/orbit/SKILL.md') if root else (home/'.agents/skills/orbit/SKILL.md')
        # Codex and Antigravity share a project skill, but global paths differ.
        if scope=='machine' or 'antigravity' not in hosts:
            same_or_create(changes,skill,ORBIT_SKILL.encode(),root or home,'Codex Orbit skill')
            add_references(skill.parent,root or home)
        if root:
            same_or_create(changes,root/'AGENTS.md',AGENTS_GUIDE.encode(),root,'Codex project guidance')
        config=(root/'.codex/config.toml') if root else (home/'.codex/config.toml')
        merge_toml(changes,config,cmd,script,root or home)
    if 'claude-code' in hosts:
        skills=(root/'.claude/skills') if root else (home/'.claude/skills')
        agents=(root/'.claude/agents') if root else (home/'.claude/agents')
        same_or_create(changes,skills/'orbit/SKILL.md',ORBIT_SKILL.encode(),root or home,'Claude Code Orbit skill')
        add_references(skills/'orbit',root or home)
        if root:
            same_or_create(changes,root/'CLAUDE.md',CLAUDE_GUIDE.encode(),root,'Claude Code guidance')
        same_or_create(changes,agents/'orbit-lead.md',ORBIT_LEAD_CLAUDE.encode(),root or home,'Claude lead agent')
        for p in (src/'agents').glob('orbit-*.md'):
            same_or_create(changes,agents/p.name,agent_claude(p.read_text('utf-8')).encode(),root or home,'Claude Code agent '+p.stem)
        config=(root/'.mcp.json') if root else (home/'.claude.json')
        merge_json(changes,config,{**common,'type':'stdio'},root or home,'Claude Code MCP configuration')
    if 'vscode' in hosts:
        if root:cfg=root/'.vscode/mcp.json'
        elif os.name=='nt':
            # A test-controlled user home must never write to the real Windows
            # roaming APPDATA outside its explicit home boundary.
            roaming=(home/'AppData/Roaming' if os.environ.get('ORBIT_SETUP_HOME')
                     else Path(os.environ.get('APPDATA',home/'AppData/Roaming')))
            cfg=roaming/'Code/User/mcp.json'
        elif sys.platform=='darwin':cfg=home/'Library/Application Support/Code/User/mcp.json'
        else:cfg=home/'.config/Code/User/mcp.json'
        merge_vscode(changes,cfg,{'type':'stdio',**common},root or home)
    return changes


def merge_vscode(changes,dest,entry,boundary):
    check_dest(dest,boundary)
    if dest.exists():
        if dest.is_symlink() or not dest.is_file():raise SetupError('Unsafe VS Code config')
        try:old=json.loads(dest.read_text(encoding='utf-8'))
        except (ValueError,UnicodeError) as exc:raise SetupError('Invalid VS Code MCP JSON') from exc
    else:old={}
    if not isinstance(old,dict) or not isinstance(old.get('servers',{}),dict):
        raise SetupError('VS Code config must contain a servers object')
    original=old.get('servers',{}).get(SERVER)
    if original is not None and original!=entry:
        if not (isinstance(original,dict) and original.get('type')=='stdio'
                and original.get('command')==entry['command'] and set(original)==set(entry)
                and isinstance(original.get('args'),list) and len(original['args'])==1
                and stock_runtime_path(original['args'][0],entry['args'][0])):
            raise SetupError('Existing VS Code Orbit server differs; manual audit required')
    updated={**old,'servers':{**old.get('servers',{}),SERVER:entry}}
    body=(json.dumps(updated,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
    action='SKIP' if dest.exists() and dest.read_bytes()==body else 'MERGE' if dest.exists() else 'CREATE'
    changes.append(Change(dest,body,action,'VS Code native stdio MCP config, preserving unrelated servers'))


def install(changes: list[Change]) -> list[str]:
    # Preflight: no contents drift since preview and no symlinks or nonfiles.
    for c in changes:
        if c.target.is_symlink():raise SetupError('Refusing symlink file: '+str(c.target))
        if c.action=='CREATE' and c.target.exists():raise SetupError('New conflict since preview: '+str(c.target))
        if c.action in {'SKIP','PRESERVE'} and (not c.target.is_file() or c.target.read_bytes()!=c.data): raise SetupError('File changed since preview: '+str(c.target))
    applied=[]
    for c in changes:
        if c.action in {'SKIP','PRESERVE'}:continue
        c.target.parent.mkdir(parents=True,exist_ok=True)
        if c.action=='CREATE':
            with c.target.open('xb') as f:f.write(c.data)
        else:
            # Existing configuration is only modified after preview. Backup first.
            if not c.target.is_file():raise SetupError('Config disappeared since preview: '+str(c.target))
            backup=c.target.with_name(c.target.name+'.orbit-backup')
            if backup.exists():
                digest=hashlib.sha256(c.target.read_bytes()).hexdigest()[:12]
                index=0
                while backup.exists():
                    index+=1
                    if index>100:raise SetupError('Too many existing backup copies')
                    backup=c.target.with_name(c.target.name+'.orbit-backup-'+digest+'-'+str(index))
            with backup.open('xb') as b:b.write(c.target.read_bytes())
            tmp=c.target.with_name(c.target.name+'.orbit-new')
            with tmp.open('xb') as f:f.write(c.data)
            tmp.replace(c.target)
            applied.append(str(backup))
        if os.name!='nt' and c.target.name in {'orbit','orbit-manager'} and c.target.parent.name=='bin' and c.target.parent.parent.name=='.orbit-universal':
            c.target.chmod(0o700)
        applied.append(str(c.target))
    return applied


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--project',type=str)
    ap.add_argument('--scope',choices=SCOPES,default='machine')
    ap.add_argument('--hosts',nargs='+',choices=HOSTS+('auto',),default=['auto'])
    ap.add_argument('--install',action='store_true',help='Apply changes only with explicit flag (preview default)')
    a=ap.parse_args()
    try:
        if a.hosts==['auto']:
            from orbit_cli import detect
            chosen=[item['host'] for item in detect(a.project) if item['detected'] and item['host'] in HOSTS]
            if not chosen:raise SetupError('No hosts detected; use --hosts to select one explicitly')
        else:
            if 'auto' in a.hosts:raise SetupError('auto cannot be mixed with explicit hosts')
            chosen=a.hosts
        changes=plan(a.project,chosen,a.scope)
        for c in changes:print(f'{c.action:7} {c.target}')
        if a.install:
            paths=install(changes)
            print(f'Installed {len(paths)} files/backups; restart selected hosts.')
        else:print('PREVIEW ONLY; nothing written. Run with --install to approve.')
    except (OSError,SetupError) as e:
        print('INSTALL BLOCKED:',str(e),file=sys.stderr)
        return 1
    return 0

if __name__=='__main__':raise SystemExit(main())
