import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import installer


class UniversalSetupTests(unittest.TestCase):
    def setUp(self):
        self.t=tempfile.TemporaryDirectory()
        self.addCleanup(self.t.cleanup)
        self.home=Path(self.t.name)/'home'
        self.old=os.environ.get('ORBIT_UNIVERSAL_HOME')
        self.old_setup=os.environ.get('ORBIT_SETUP_HOME')
        os.environ['ORBIT_UNIVERSAL_HOME']=str(self.home)
        # Installer also maintains a launcher under user_home(), distinct
        # from runtime_folder(). Keep all tests away from the real OS home.
        os.environ['ORBIT_SETUP_HOME']=str(self.home)
        self.addCleanup(self.restore)
        self.project=Path(self.t.name)/'orbit-todo-lab';self.project.mkdir()

    def restore(self):
        if self.old is None:os.environ.pop('ORBIT_UNIVERSAL_HOME',None)
        else:os.environ['ORBIT_UNIVERSAL_HOME']=self.old
        if self.old_setup is None:os.environ.pop('ORBIT_SETUP_HOME',None)
        else:os.environ['ORBIT_SETUP_HOME']=self.old_setup

    def test_prior_edge_qa_candidate_is_safe_for_backed_up_upgrade(self):
        # Previous official c027e73 browser-fix candidate was omitted from
        # stock upgrade digests. Never accept unrecognized custom content.
        prior={
            'source/runtime/orbit_mcp.py': '8fb102a9b367332ef92d9f1204e69996f6ef1bee033354dd1971735ccd46ba1a',
            'source/runtime/orbit_browser.py': '56b544b943add6fe3a321ed74f694de0059b35a1fe1a497195d81560b6a7b31f',
            'source/runtime/orbit_build.py': '5310720aa06c6d44a4cd18065f2b6da74b1284e4478f12e7be7a5aba1679276f',
            'source/skills/orbit/references/HANDOFF.md': '88ac4083b7fea0739355812f9f8c0d83c0e24591c23a96fdec025f8521c508a6',
            'source/skills/orbit/references/TASK-LIFECYCLE.md': 'de6db388c651f35cb4f93db887e7f27b5453ea37e0184a1717a933e1f40b560c',
        }
        for path, digest in prior.items():
            with self.subTest(path=path):
                self.assertIn(digest, installer.OLD_STOCK_SHA256)
        self.assertNotIn('0' * 64, installer.OLD_STOCK_SHA256)

    def test_role_skill_preferences_have_safe_fallback(self):
        from source.runtime import orbit_capabilities as cap
        outcome=cap.select(self.project,'orbit-security: audit app security',[],home=self.home)
        policy=outcome['role_skill_preferences']
        self.assertEqual(policy['role'],'orbit-security')
        self.assertIn('static-analysis',[r['name'] for r in policy['preferred_skills']])
        self.assertIn('native host tools',policy['fallback'])
        self.assertTrue(all(r['status']=='NOT_INSTALLED' for r in policy['preferred_skills']))
        self.assertFalse((self.project/'.agents/skills/static-analysis').exists())

    def test_recognizes_prior_v024_stock_runtime(self):
        # We do not store previous binary distributions in test fixtures, but
        # these digests identify precisely the published v0.24 test candidate.
        hashes = installer.OLD_STOCK_SHA256
        self.assertIn('1e384ca291c3fe20cc2a866f103abbc3139c1c5feffc250c3e6999975dc3754a', hashes)
        self.assertIn('508186df8c690bb3c64b147a5163399e42824ac251543a82f5482c427331171a', hashes)

    def test_preview_does_not_write(self):
        changes=installer.plan(self.project,scope='project')
        self.assertGreater(len(changes),28)
        self.assertEqual(list(self.project.iterdir()),[])
        self.assertFalse(self.home.exists())

    def test_install_and_repeat_skip(self):
        ch=installer.plan(self.project,scope='project')
        installer.install(ch)
        self.assertTrue((self.project/'.agents/agents/orbit.md').exists())
        self.assertTrue((self.project/'.claude/agents/orbit-frontend.md').exists())
        self.assertTrue((self.project/'.codex/config.toml').exists())
        self.assertTrue((self.home/'0.28.0/orbit_delivery.py').is_file())
        self.assertEqual(set(c.action for c in installer.plan(self.project,scope='project')),{'SKIP'})

    def test_existing_customization_refused(self):
        p=self.project/'.agents/agents/orbit.md';p.parent.mkdir(parents=True);p.write_text('customized')
        with self.assertRaises(installer.SetupError):installer.plan(self.project,scope='project')
        self.assertEqual(p.read_text(),'customized')

    def test_merge_json_preserves_other_servers(self):
        p=self.project/'.mcp.json';p.write_text(json.dumps({'mcpServers':{'other':{'command':'something'}}}))
        installer.install(installer.plan(self.project,scope='project'))
        cfg=json.loads(p.read_text())
        self.assertIn('other',cfg['mcpServers']);self.assertIn('orbit-core-native',cfg['mcpServers'])
        self.assertTrue((self.project/'.mcp.json.orbit-backup').exists())

    def test_codex_toml_preserves_existing_settings(self):
        p=self.project/'.codex/config.toml';p.parent.mkdir();p.write_text('model = "gpt-6"\n')
        installer.install(installer.plan(self.project,scope='project'))
        self.assertIn('model = "gpt-6"',p.read_text())
        self.assertIn('[mcp_servers."orbit-core-native"]',p.read_text())
        self.assertTrue((p.with_name('config.toml.orbit-backup')).exists())

    def test_product_kit_adoption_reference_is_installed_without_its_runner(self):
        installer.install(installer.plan(self.project,scope='project'))
        for parent in ('.agents/skills', '.claude/skills'):
            dest=self.project/parent/'orbit'/'references'/'PRODUCT-KIT-ADOPTION.md'
            self.assertTrue(dest.is_file())
            self.assertIn('recover',dest.read_text(encoding='utf-8'))
        self.assertFalse((self.project/'.agents/product-kit').exists())
        self.assertFalse((self.project/'.agents/product-kit/kit.mjs').exists())

    def test_fresh_install_includes_guided_intake_and_doc_references(self):
        installer.install(installer.plan(self.project,scope='project'))
        for host_dir in ('.agents/skills', '.claude/skills'):
            base=self.project/host_dir/'orbit'
            self.assertTrue((base/'references/PROJECT-INTAKE.md').is_file())
            self.assertTrue((base/'references/DOCS-AND-CONTEXT.md').is_file())
            content=(base/'SKILL.md').read_text(encoding='utf-8')
            self.assertIn('PROJECT-INTAKE.md',content)
            self.assertIn('DOCS-AND-CONTEXT.md',content)
        self.assertFalse((self.project/'.orbit').exists())
        self.assertFalse((self.project/'docs').exists())

    def test_only_selected_host(self):
        installer.install(installer.plan(self.project,['codex'],scope='project'))
        self.assertTrue((self.project/'.agents/skills/orbit/SKILL.md').exists())
        self.assertFalse((self.project/'.claude').exists())
        self.assertFalse((self.project/'.agents/agents').exists())

    def test_reject_root_and_symlink(self):
        with self.assertRaises(installer.SetupError):installer.plan(self.project.anchor,scope='project')
        p=Path(self.t.name)/'linked'
        try:
            p.symlink_to(self.project,target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("Symlinks require elevated privileges on this system")
        with self.assertRaises(installer.SetupError):installer.plan(p,scope='project')

    def test_project_manifest_configs_valid(self):
        installer.install(installer.plan(self.project,scope='project'))
        for p in [self.project/'.mcp.json',self.project/'.agents/mcp_config.json']:
            entry=json.loads(p.read_text())['mcpServers']['orbit-core-native']
            self.assertTrue(Path(entry['args'][0]).is_file())
            self.assertTrue(Path(entry['command']).is_file())
            self.assertTrue((installer.runtime_folder()/'orbit_preview.py').is_file())
        self.assertEqual(len(list((self.project/'.claude/agents').glob('orbit-*.md'))),13)
        self.assertEqual(len(list((self.project/'.agents/agents').glob('*.md'))),13)

    def test_mcp_process_and_shared_db(self):
        ch=installer.plan(self.project,['codex'],scope='project');installer.install(ch)
        exe=installer.python_binary();server=installer.runtime_folder()/'orbit_mcp.py'
        db=Path(self.t.name)/'test-shared.sqlite'
        def rpc(msgs):
            lines=''.join(json.dumps(x)+'\n' for x in msgs)
            run=subprocess.run([exe,str(server)],input=lines,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,
                env={**os.environ,'ORBIT_LOCAL_DB':str(db)},timeout=12)
            self.assertEqual(run.returncode,0,run.stderr)
            return [json.loads(x) for x in run.stdout.splitlines()]
        def req(i,method,params=None):return {'jsonrpc':'2.0','id':i,'method':method,'params':params or {}}
        def call(i,name,args):return req(i,'tools/call',{'name':name,'arguments':args})
        initial=rpc([req(1,'initialize',{'protocolVersion':'2025-11-25'}),req(2,'tools/list')])
        self.assertEqual(len(initial[1]['result']['tools']),47)
        def tooldata(r):return json.loads(r['result']['content'][0]['text'])
        save_args={'project':'orbit-todo-lab','key':'goal','kind':'decision','summary':'Local SQLite API, no cloud sync','source':'test','confirm_write':True}
        result=rpc([call(3,'orbit_memory_save',save_args)])[0]
        self.assertFalse(result['result']['isError'])
        later=rpc([call(4,'orbit_memory_recall',{'project':'orbit-todo-lab'})])[0]
        self.assertIn('Local SQLite API',str(tooldata(later)))
        other=rpc([call(5,'orbit_memory_recall',{'project':'other-project'})])[0]
        self.assertNotIn('Local SQLite API',str(tooldata(other)))

    def test_mcpb_structure(self):
        import zipfile
        bundle_path = ROOT / f'ORBIT-Claude-Desktop-v{installer.VERSION}.mcpb'
        if not bundle_path.exists():
            import scripts.prepare_release_candidate as prep
            prep.prepare(ROOT)
        with zipfile.ZipFile(bundle_path) as z:
            m=json.loads(z.read('manifest.json'))
            self.assertEqual(m['server']['type'],'python')
            self.assertEqual(len(m['tools']),34)
            self.assertIn('server/orbit_mcp.py',z.namelist())
            self.assertIn('server/orbit_tasks.py',z.namelist())
            self.assertIn('server/orbit_capabilities.py',z.namelist())
            self.assertIn('server/orbit_preview.py',z.namelist())
            self.assertIn('server/orbit_browser.py',z.namelist())
            self.assertIn('server/orbit_build.py',z.namelist())
            self.assertIn('server/orbit_intake.py',z.namelist())



    def test_machine_install_all_hosts_idempotent(self):
        before=os.environ.get('ORBIT_SETUP_HOME')
        os.environ['ORBIT_SETUP_HOME']=str(Path(self.t.name)/'user')
        self.addCleanup(lambda: os.environ.pop('ORBIT_SETUP_HOME',None) if before is None else os.environ.__setitem__('ORBIT_SETUP_HOME',before))
        c=installer.plan(scope='machine')
        self.assertGreater(len(c),25)
        installer.install(c)
        home=Path(os.environ['ORBIT_SETUP_HOME'])
        self.assertTrue((home/'.gemini/config/agents/orbit-frontend.md').exists())
        self.assertTrue((home/'.gemini/config/skills/orbit/SKILL.md').exists())
        self.assertTrue((home/'.agents/skills/orbit/SKILL.md').exists())
        self.assertTrue((home/'.claude/skills/orbit/SKILL.md').exists())
        self.assertTrue((home/'.claude/agents/orbit-backend.md').exists())
        self.assertTrue((home/'.gemini/config/mcp_config.json').exists())
        self.assertTrue((home/'.codex/config.toml').exists())
        self.assertTrue((home/'.claude.json').exists())
        self.assertEqual({x.action for x in installer.plan(scope='machine')},{'SKIP'})
        self.assertEqual(list(self.project.iterdir()),[])

    def test_existing_owner_guidance_preserved(self):
        (self.project/'AGENTS.md').write_text('my personal rules')
        (self.project/'CLAUDE.md').write_text('my other rules')
        c=installer.plan(self.project,scope='project')
        self.assertEqual(sum(x.action=='PRESERVE' for x in c),2)
        installer.install(c)
        self.assertEqual((self.project/'AGENTS.md').read_text(),'my personal rules')
        self.assertEqual((self.project/'CLAUDE.md').read_text(),'my other rules')

    def test_capability_selector_finds_vetted_local_and_external_candidate(self):
        from source.runtime import orbit_capabilities as cap
        skill=self.project/'.agents/skills/ui-polish/SKILL.md'
        skill.parent.mkdir(parents=True)
        skill.write_text('---\nname: ui-polish\ndescription: Improve frontend UI design and layout with accessibility\n---\n# Local skill\n')
        report=cap.select(self.project,'Improve our frontend UI layout and design',[],home=self.home)
        self.assertEqual(report['installed_matches'][0]['name'],'ui-polish')
        self.assertTrue(any(x['name']=='impeccable' for x in report['external_research_candidates']))
        self.assertIn('REUSE',report['recommended_action'])
        self.assertEqual(len(list((self.project/'.agents/skills/ui-polish').iterdir())),1)

    def test_optional_agent_browser_provider_is_discovered_without_install(self):
        from source.runtime import orbit_capabilities as cap
        report=cap.select(self.project,'Run browser E2E screenshots',[],home=self.home)
        self.assertEqual(report['optional_browser_provider']['status'],'NOT_CONFIGURED')
        self.assertTrue(any(x['name']=='agent-browser' and x['kind']=='mcp'
                            for x in report['external_research_candidates']))
        self.assertFalse((self.project/'.agents/skills/agent-browser').exists())
        cfg=self.project/'.mcp.json'
        cfg.write_text(json.dumps({'mcpServers':{'agent-browser':{'command':'agent-browser','args':['mcp']}}}))
        reported=cap.select(self.project,'Run browser E2E screenshots',[],home=self.home)
        self.assertEqual(reported['optional_browser_provider']['status'],'CONFIGURED_UNVERIFIED')
        self.assertEqual(reported['configured_mcp_servers'][0]['name'],'agent-browser')
        visible=cap.select(self.project,'Test Todo interactions', ['agent_browser_snapshot'], home=self.home)
        self.assertEqual(visible['optional_browser_provider']['status'],'HOST_REPORTED_TOOL_VISIBLE')
        self.assertIn('Playwright PASS',visible['optional_browser_provider']['orbit_browser_qa_gate'])

    def test_browser_workflow_prefers_host_browser_then_computer_use(self):
        from unittest.mock import patch
        from source.runtime import orbit_capabilities as cap
        with patch('source.runtime.orbit_capabilities.importlib.util.find_spec', return_value=None), \
             patch('source.runtime.orbit_capabilities.shutil.which', return_value=None):
            tools=['browser_navigate','browser_snapshot','computer_use_click','agent_browser_open']
            result=cap.select(self.project,'orbit-qa: test web app in browser',tools,home=self.home)
            wf=result['browser_workflow']
            self.assertEqual(wf['preferred']['id'],'host_browser')
            self.assertEqual(wf['preferred']['status'],'HOST_REPORTED_ACTION_TOOL')
            self.assertFalse(wf['execution_verified'])
            self.assertFalse(wf['install_performed'])
            self.assertIn('Playwright',wf['qa_gate'])
            computer=cap.select(self.project,'orbit-qa: check web browser',[
                'computer_use_click','computer_screenshot'],home=self.home)
            self.assertEqual(computer['browser_workflow']['preferred']['id'],'host_computer_use')
            browser_use=cap.select(self.project,'orbit-qa: use browser',[
                'browser_use_open','browser_use_snapshot'],home=self.home)
            self.assertEqual(browser_use['browser_workflow']['preferred']['id'],'host_browser_use')
            vercel=cap.select(self.project,'orbit-qa: browser UI tests',[
                'agent_browser_open','agent_browser_snapshot'],home=self.home)
            self.assertEqual(vercel['browser_workflow']['preferred']['id'],'vercel_agent_browser')
            self.assertIn('explicit permission',vercel['browser_workflow']['privacy'])

    def test_browser_workflow_does_not_promote_screenshot_only_or_configured_mcp(self):
        from unittest.mock import patch
        from source.runtime import orbit_capabilities as cap
        cfg=self.project/'.mcp.json'
        cfg.write_text(json.dumps({'mcpServers':{'agent-browser':{'command':'agent-browser','args':['mcp']}}}))
        with patch('source.runtime.orbit_capabilities.importlib.util.find_spec', return_value=None), \
             patch('source.runtime.orbit_capabilities.shutil.which', return_value=None):
            result=cap.select(self.project,'orbit-qa: browser testing',[
                'browser_snapshot','computer_use_screenshot','browser_use_screenshot',
                'agent_browser_snapshot'],home=self.home)
            wf=result['browser_workflow']
            self.assertIsNone(wf['preferred'])
            self.assertEqual(wf['providers'][0]['status'],'INSUFFICIENT_TOOLS')
            self.assertEqual(wf['providers'][1]['status'],'INSUFFICIENT_TOOLS')
            self.assertEqual(wf['providers'][2]['status'],'INSUFFICIENT_TOOLS')
            self.assertEqual(wf['providers'][4]['status'],'CONFIGURED_OR_INSTALLED_REVIEW_REQUIRED')
            self.assertEqual(result['optional_browser_provider']['status'],'HOST_REPORTED_TOOL_VISIBLE')
            self.assertEqual(cap.select(self.project,'Write short docs',[],home=self.home)['browser_workflow'],None)

    def test_browser_workflow_local_fallback_and_mcp_namespaced_tools(self):
        from unittest.mock import patch
        from source.runtime import orbit_capabilities as cap
        def find_exe(name):
            return '/usr/bin/google-chrome' if name=='google-chrome' else None
        with patch('source.runtime.orbit_capabilities.importlib.util.find_spec', return_value=object()), \
             patch('source.runtime.orbit_capabilities.shutil.which', side_effect=find_exe):
            result=cap.select(self.project,'orbit-qa: browser testing',[],home=self.home)
            wf=result['browser_workflow']
            self.assertEqual(wf['preferred']['id'],'local_playwright')
            self.assertIn('chrome',wf['providers'][3]['browsers_detected'])
            namespaced=cap.select(self.project,'orbit-qa: browser testing',[
                'mcp__playwright__browser_navigate','mcp__agent_browser__open'],home=self.home)
            self.assertEqual(namespaced['browser_workflow']['preferred']['id'],'host_browser')
            self.assertEqual(namespaced['browser_workflow']['providers'][4]['status'],'HOST_REPORTED_ACTION_TOOL')

    def test_m3_denied_browser_permission_must_not_reroute_to_another_provider(self):
        from unittest.mock import patch
        sys.path.insert(0,str(ROOT/'source/runtime'))
        import orbit_mcp
        from source.runtime import orbit_capabilities as cap
        with (patch('source.runtime.orbit_capabilities.importlib.util.find_spec',return_value=object()),
              patch('source.runtime.orbit_capabilities.shutil.which',return_value='/usr/bin/chrome')):
            tools=['browser_navigate','computer_use_click','agent_browser_open']
            denied=cap.select(self.project,'orbit-qa: test browser',tools,
                              home=self.home,permission_state='DENIED')
            plan=denied['browser_workflow']
            self.assertEqual(plan['decision'],'HOLD_PERMISSION_DENIED')
            self.assertIsNone(plan['preferred'])
            self.assertFalse(plan['permission_verified'])
            self.assertEqual(denied['recommended_action'],'HOLD_PERMISSION_DENIED')
            self.assertIn('Do not invoke any fallback',plan['next_action'])
            self.assertIn('Never bypass',plan['fallback'])
            self.assertFalse(plan['execution_verified'])
            # A reported approval never becomes a trusted verification claim.
            approved=cap.select(self.project,'orbit-qa: browser testing',tools,
                                home=self.home,permission_state='APPROVED')
            self.assertEqual(approved['browser_workflow']['preferred']['id'],'host_browser')
            self.assertFalse(approved['browser_workflow']['permission_verified'])
            ordinary=cap.select(self.project,'orbit-qa: browser testing',tools,home=self.home)
            self.assertEqual(ordinary['browser_workflow']['permission_state'],'UNKNOWN')
        with self.assertRaisesRegex(ValueError,'permission_state'):
            cap.select(self.project,'orbit-qa: browser testing',[],
                       home=self.home,permission_state='BYPASS')
        self.assertIn('permission_state',orbit_mcp.TOOL_MAP['orbit_capability_select']['properties'])
        valid={'project_root':str(self.project),'objective':'browser test','permission_state':'DENIED'}
        orbit_mcp.validate('orbit_capability_select',valid)
        with self.assertRaises(ValueError):
            orbit_mcp.validate('orbit_capability_select',{**valid,'permission_state':'SILENT_OVERRIDE'})

    def test_m4_adaptive_context_and_host_tool_is_always_unverified(self):
        from source.runtime import orbit_capabilities as cap
        skill=self.project/'.agents/skills/local-ui-review/SKILL.md'
        skill.parent.mkdir(parents=True)
        skill.write_text('---\nname: local-ui-review\ndescription: UI design and layout review\n---\nlocal') 
        simple=cap.select(self.project,'Fix frontend component layout',
                          ['spawn_agent'],home=self.home)
        plan=simple['adaptive_workflow']
        self.assertEqual(plan['workflow_mode'],'FOCUSED')
        self.assertEqual(plan['context']['mode'],'COMPACT_RESUME')
        self.assertTrue(plan['context']['compact'])
        self.assertEqual(plan['context']['max_chars'],1500)
        self.assertEqual(plan['execution']['decision'],'VERIFY_NATIVE_HOST_TOOL')
        self.assertEqual(plan['execution']['native_tool_hint'],'spawn_agent')
        self.assertFalse(plan['execution']['host_tool_verified'])
        self.assertFalse(plan['execution']['permission_verified'])
        self.assertFalse(plan['execution']['agent_invoked'])
        self.assertEqual(plan['execution']['model_choice'],'HOST_CONTROLLED')
        self.assertEqual(plan['skill_review']['candidate'],'local-ui-review')
        self.assertFalse(plan['skill_review']['auto_install'])
        self.assertLess(len(json.dumps(plan,ensure_ascii=True)),1600)
        self.assertFalse((self.project/'.agents/skills/agent-browser').exists())

    def test_m4_risk_and_multistage_do_not_silently_use_compact_context(self):
        from source.runtime import orbit_capabilities as cap
        high=cap.select(self.project,'Deploy production backend security migration',
                        ['invoke_subagent'],home=self.home)
        p=high['adaptive_workflow']
        self.assertEqual(p['workflow_mode'],'HIGH_RISK_REVIEW')
        self.assertEqual(p['context']['mode'],'FULL_REVIEW')
        self.assertIsNone(p['context']['max_chars'])
        self.assertEqual(p['execution']['decision'],'HOST_APPROVAL_AND_REVIEW_REQUIRED')
        self.assertFalse(p['execution']['agent_invoked'])
        broad=cap.select(self.project,'Redesign the entire mobile platform architecture',
                         ['spawn_agent'],home=self.home)['adaptive_workflow']
        self.assertEqual(broad['workflow_mode'],'MULTI_STAGE')
        self.assertEqual(broad['context']['mode'],'FULL_REVIEW')
        serial=cap.select(self.project,'Fix a small backend bug',[],
                          home=self.home)['adaptive_workflow']
        self.assertEqual(serial['workflow_mode'],'FOCUSED')
        self.assertEqual(serial['execution']['decision'],'HOST_SERIAL_FALLBACK')
        self.assertIsNone(serial['execution']['native_tool_hint'])
        denied=cap.select(self.project,'Fix small UI component', ['spawn_agent'],
                          home=self.home,permission_state='DENIED')
        blocked=denied['adaptive_workflow']
        self.assertEqual(blocked['execution']['decision'],'HOLD_PERMISSION_DENIED')
        self.assertIsNone(blocked['execution']['native_tool_hint'])
        self.assertFalse(blocked['execution']['permission_verified'])
        self.assertEqual(denied['recommended_action'],'HOLD_PERMISSION_DENIED')

    def test_optional_provider_upgrade_hashes_recognized(self):
        self.assertIn('0f929f83c43c11b46a666387dd3d7581e081876a4cf401e2f2928b1a3f97f85c',installer.OLD_STOCK_SHA256)
        self.assertIn('81bcd52a57163a9b071212a02ca9421a4df832ef6cfbaee9ff62dc46dc19aaa1',installer.OLD_STOCK_SHA256)

    def test_capability_tool_stdio_and_no_auto_install(self):
        installer.install(installer.plan(self.project,['codex'],scope='project'))
        exe=installer.python_binary();server=installer.runtime_folder()/'orbit_mcp.py'
        msgs=[{'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':'orbit_capability_select','arguments':{'project_root':str(self.project),'objective':'polish frontend design'}}}]
        p=subprocess.run([exe,str(server)],input=json.dumps(msgs[0])+'\n',text=True,capture_output=True,timeout=12,env={**os.environ,'ORBIT_LOCAL_DB':str(Path(self.t.name)/'test2.sqlite')})
        self.assertEqual(p.returncode,0,p.stderr)
        result=json.loads(json.loads(p.stdout)['result']['content'][0]['text'])
        self.assertEqual(result['recommended_action'],'BROWSE_OFFICIAL_SOURCES_AND_REQUEST_APPROVAL')
        self.assertEqual(result['external_research_candidates'][0]['name'],'impeccable')
        self.assertFalse((self.project/'.agents/skills/impeccable').exists())

    def test_preview_runtime_is_installed_and_present(self):
        installer.install(installer.plan(self.project,['codex'],scope='project'))
        r = installer.runtime_folder()
        self.assertTrue((r/'orbit_preview.py').exists())
        self.assertTrue((r/'orbit_browser.py').exists())
        self.assertTrue((r/'orbit_build.py').exists())
        self.assertIn(installer.VERSION,str(r))

    def test_stock_v023_runtime_upgrade(self):
        old = Path(__file__).resolve().parents[2]/'orbit-core-mcp-v0.23.0-git/source/runtime/orbit_mcp.py'
        if not old.exists():
            self.skipTest('Prior version source unavailable in this checkout')
        runtime = installer.runtime_folder()
        runtime.mkdir(parents=True)
        (runtime/'orbit_mcp.py').write_bytes(old.read_bytes())
        changes=installer.plan(self.project,['codex'],scope='project')
        self.assertIn('UPGRADE',[c.action for c in changes])
        installer.install(changes)
        self.assertEqual((runtime/'orbit_mcp.py.orbit-backup').read_bytes(),old.read_bytes())
        self.assertTrue((runtime/'orbit_preview.py').exists())

    def test_machine_config_preserves_other_servers(self):
        prior=os.environ.get('ORBIT_SETUP_HOME')
        os.environ['ORBIT_SETUP_HOME']=str(Path(self.t.name)/'usr')
        self.addCleanup(lambda: os.environ.pop('ORBIT_SETUP_HOME',None) if prior is None else os.environ.__setitem__('ORBIT_SETUP_HOME',prior))
        conf=Path(os.environ['ORBIT_SETUP_HOME'])/'.claude.json';conf.parent.mkdir(parents=True)
        conf.write_text(json.dumps({'mcpServers':{'other':{'command':'my-existing'}}}))
        installer.install(installer.plan(scope='machine'))
        data=json.loads(conf.read_text())
        self.assertIn('other',data['mcpServers'])
        self.assertIn('orbit-core-native',data['mcpServers'])

    def test_exact_v022_stock_upgrade_does_not_delete_project(self):
        old=Path(__file__).resolve().parent/'fixtures/v0.22.0'
        if not old.is_dir():self.skipTest('No v0.22 stock test fixture')
        stock=(old/'source/agents/orbit-frontend.md').read_bytes()
        dest=self.project/'.agents/agents/orbit-frontend.md';dest.parent.mkdir(parents=True)
        dest.write_bytes(stock)
        planned=installer.plan(self.project,scope='project')
        self.assertIn('UPGRADE',[x.action for x in planned])
        installer.install(planned)
        self.assertNotEqual(dest.read_bytes(),stock)
        self.assertEqual((dest.with_name(dest.name+'.orbit-backup')).read_bytes(),stock)

if __name__=='__main__':unittest.main()
