from harness import *
from transport_repair import repair

def recheck():
    assert (R/'evidence'/'phase_b_completed.json').exists(), 'Paired pipeline must finish first: no parallel Maven'
    lock=json.loads((R/'samples'/'sample_lock.json').read_text())
    cache=R/'tools'/'java-user-home'/'.m2'/'repository';cache.mkdir(parents=True,exist_ok=True)
    measured=R/'tools'/'cache'/'m4'
    for s in lock['samples']:
        sid=s['id'];out=R/'mvnup'/sid/'m4-r2'/'mvnup'
        if (out/'baseline-integrity.json').exists():continue
        budget();out.mkdir(parents=True,exist_ok=True);seed=[]
        for p in measured.rglob('*'):
            if not p.is_file():continue
            rel=p.relative_to(measured)
            if any('SNAPSHOT' in x for x in rel.parts) or p.name.startswith('maven-metadata') or p.suffix in ['.lastUpdated','.lock','.tmp']:continue
            dest=cache/rel
            if not dest.exists():
                dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest);seed.append({'path':rel.as_posix(),'sha256':sha(dest)})
        dump(out/'standalone-cache-seeding.json',seed)
        src=R/'samples'/'sources'/sid;before=snapshot_sources(src)
        paths,e=runtime_env('m4');e.update(GIT_CONFIG_COUNT='1',GIT_CONFIG_KEY_0='safe.directory',GIT_CONFIG_VALUE_0=src.as_posix())
        settings=R/'protocol'/'settings.xml'
        argv=[str(Path(paths['m4'])/'bin'/'mvnup.cmd'),'check','-B','--color','never','--directory',str(src),'-s',str(settings),'-gs',str(settings),f'-Dmaven.repo.local={measured}']
        for attempt in range(3):
            rec=run(argv,src,out,e,timeout=180)
            log=(out/'stdout.txt').read_text(errors='replace')+(out/'stderr.txt').read_text(errors='replace')
            if attempt==2 or not re.search(r'handshake|Could not transfer|Connection reset|connect timed out',log,re.I):break
            archived=out/f'infra-attempt-{attempt+1}';archived.mkdir(exist_ok=True)
            for name in ['command.json','stdout.txt','stderr.txt']:shutil.copy2(out/name,archived/name)
            dump(archived/'standalone-cache-artifacts.json',inventory(cache));repair(log,cache,archived)
            for marker in cache.rglob('*.lastUpdated'):
                assert marker.resolve().is_relative_to(cache.resolve())
                dest=archived/'failure-markers'/marker.relative_to(cache);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(marker,dest);marker.unlink()
        dump(out/'environment.json',{k:e[k] for k in ['JAVA_HOME','MAVEN_HOME','MAVEN_USER_HOME','MAVEN_SKIP_RC','MAVEN_OPTS','TEMP','TMP','PATH']})
        dump(out/'standalone-cache-artifacts.json',inventory(cache));dump(out/'cache-artifacts.json',inventory(measured))
        dump(out/'baseline-integrity.json',{'source_unchanged':before==snapshot_sources(src),'exit_code':rec['exit_code'],'timeout':rec['timeout'],'actual_standalone_cache':str(cache),'finished_utc':utc()})
        lines=log.splitlines()
        dump(out/'extracted-messages.json',{'warnings':[x for x in lines if 'WARN' in x],'errors':[x for x in lines if 'ERROR' in x],'recommendation_lines':[x for x in lines if re.search('upgrad|replac|recommend|compatib|change',x,re.I)],'exit_code':rec['exit_code'],'timeout':rec['timeout']})
        print('BASELINE_RECHECK',sid,rec['exit_code'],rec['timeout'],flush=True)
    dump(R/'evidence'/'baseline_recheck_completed.json',{'finished_utc':utc(),'repositories':30})
if __name__=='__main__':recheck()
