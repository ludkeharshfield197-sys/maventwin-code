from harness import *
def verify():
    lock=json.loads((R/'samples'/'sample_lock.json').read_text());issues=[];commands=[]
    if sha(R/'samples'/'samples_v1.csv')!=lock['samples_csv_sha256']:issues.append('SAMPLE_CSV_CHANGED')
    if len(lock['samples'])!=30 or len({s['repo'] for s in lock['samples']})!=30:issues.append('NOT_30_DISTINCT_REPOSITORIES')
    if len({s['commit'] for s in lock['samples']})!=30:issues.append('COMMIT_ALIAS_DUPLICATION')
    for phase in ['metadata_diff','mvnup']:
        for p in (R/phase).rglob('command.json'):
            d=json.loads(p.read_text());commands.append({'file':p.relative_to(R).as_posix(),'runtime_started':d['started_utc'],'exit_code':d['exit_code'],'timeout':d['timeout']})
            for name,key in [('stdout.txt','stdout_sha256'),('stderr.txt','stderr_sha256')]:
                if sha(p.parent/name)!=d[key]:issues.append(str(p)+': '+key+' MISMATCH')
            if any(a in ['test','package','clean','install','deploy','compile','test-compile','verify'] for a in d['argv'][1:]):issues.append(str(p)+': UNAUTHORIZED_GOAL')
            if 'm4-r' in str(p) and d['started_utc']<lock['frozen_utc']:issues.append(str(p)+': M4_BEFORE_LOCK')
    expected_metadata=0;expected_baselines=0
    runtime_paths=json.loads((R/'protocol/runtime_paths.json').read_text())
    for s in lock['samples']:
        for rt in ['m3','m4']:
            for n in [1,2]:
                for kind in ['model','tree','mediation','validate']:
                    base=R/'metadata_diff'/s['id']/f'{rt}-r{n}'/kind
                    for name in ['command.json','stdout.txt','stderr.txt','environment.json','cache-artifacts.json']:
                        if not (base/name).exists():issues.append(str(base/name)+': MISSING')
                    expected_metadata+=int((base/'command.json').exists())
                    if (base/'environment.json').exists() and json.loads((base/'environment.json').read_text(encoding='utf-8')).get('JAVA_HOME')!=runtime_paths['jdk']:issues.append(str(base)+': JDK_CHANGED')
        for n in [1,2]:
            base=R/'mvnup'/s['id']/f'm4-r{n}'/'mvnup'
            expected_baselines+=int((base/'command.json').exists())
        for p in [R/'metadata_diff'/s['id']/'semantic-adjudication.json',R/'mvnup'/s['id']/'adjudication.json']:
            if not p.exists():issues.append(str(p)+': MISSING_ADJUDICATION')
        bp=R/'mvnup'/s['id']/'m4-r2/mvnup/baseline-integrity.json'
        if not bp.exists() or not json.loads(bp.read_text()).get('source_unchanged'):issues.append(s['id']+': BASELINE_SOURCE_INTEGRITY')
    if expected_metadata!=480:issues.append('NOT_480_PAIRED_COMMANDS')
    if expected_baselines!=60:issues.append('NOT_60_BASELINE_COMMANDS')
    integrity=[]
    for s in lock['samples']:
        sid=s['id'];pom=R/'samples'/'sources'/sid/'pom.xml'
        src=pom.parent;okay=sha(pom)==s['pom_sha256']
        current_commit=subprocess.check_output(['git','-c',f'safe.directory={src.as_posix()}','-C',str(src),'rev-parse','HEAD'],text=True).strip()
        source_digest=hashlib.sha256(json.dumps(snapshot_sources(src),sort_keys=True).encode()).hexdigest()
        source_unchanged=source_digest==s['source_manifest_sha256']
        integrity.append({'id':sid,'root_pom_unchanged':okay,'commit_unchanged':current_commit==s['commit'],'source_manifest_unchanged':source_unchanged})
        if not okay:issues.append(sid+': POM_CHANGED')
        if current_commit!=s['commit']:issues.append(sid+': COMMIT_CHANGED')
        if not source_unchanged:issues.append(sid+': SOURCE_MANIFEST_CHANGED')
    for required in ['phase_b_completed.json','baseline_recheck_completed.json']:
        if not (R/'evidence'/required).exists():issues.append('NOT_COMPLETE: '+required)
    rows=json.loads((R/'metrics'/'repo_results.json').read_text())
    if len(rows)!=30:issues.append('NOT_ALL_30_CLASSIFIED')
    actual=size()
    if actual>=15_000_000_000:issues.append('DATA_LIMIT_EXCEEDED')
    out={'verified_utc':utc(),'sample_count':len(lock['samples']),'paired_canonical_commands':expected_metadata,'baseline_canonical_commands':expected_baselines,'recorded_final_commands':len(commands),'new_data_bytes':actual,'new_data_GB_decimal':actual/1e9,'issues':issues,'commands':commands,'root_pom_integrity':integrity,'not_tested':'Full builds/tests/artifacts; full reactors outside root-POM units.'}
    dump(R/'verification'/'final-audit.json',out);print(json.dumps({k:v for k,v in out.items() if k not in ['commands','root_pom_integrity']},indent=2));return out
if __name__=='__main__':verify()
