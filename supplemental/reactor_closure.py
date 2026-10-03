from reactor_followup import *

def main():
    sid='eclipse-ee4j__angus-activation';area='reactor_closure';base=OUT/area/sid
    cache=fresh_cache(area,seed=OUT/'reactor_central_materialized'/sid/'frozen_repository')
    original=OUT/'sources'/sid
    log=(OUT/'reactor_central_materialized'/sid/'runs/m3-r1/stdout.txt').read_text(encoding='utf-8',errors='replace')
    for attempt in range(8):
        missing=set(re.findall(r'artifact ([\w.]+):([\w.-]+):(jar|pom):([\w.-]+)',log))
        if not missing:break
        for g,a,typ,v in sorted(missing):fetch_artifact(cache,g,a,v,typ)
        source=OUT/'reactor_sources'/sid/f'{area}-materialization-{attempt}'
        copy_tree(original,source,ignore=shutil.ignore_patterns('.git','target'))
        rec=maven('m3',Path(RT['jdk']),source,cache,base/f'materialization-{attempt}',['package','-DskipTests=false','-Dmaven.javadoc.skip=true'],recursive=True,timeout=180)
        if rec['exit_code']==0:break
        log=(base/f'materialization-{attempt}/stdout.txt').read_text(encoding='utf-8',errors='replace')
    frozen=base/'frozen_repository';copy_tree(cache,frozen);dump(base/'frozen_manifest.json',manifest(frozen))
    for rt,n in [('m3',1),('m4',1),('m4',2),('m3',2)]:
        source=OUT/'reactor_sources'/sid/f'{area}-{rt}-r{n}';copy_tree(original,source,ignore=shutil.ignore_patterns('.git','target'))
        arm=fresh_cache(f'{area}-{rt}-{n}',seed=frozen);out=base/'runs'/f'{rt}-r{n}'
        maven(rt,Path(RT['jdk']),source,arm,out,['package','-DskipTests=false','-Dmaven.javadoc.skip=true'],recursive=True,timeout=240)
        reports=[]
        for p in source.rglob('TEST-*.xml'):
            r=ET.parse(p).getroot();reports.append(dict(path=p.relative_to(source).as_posix(),tests=r.get('tests'),failures=r.get('failures'),errors=r.get('errors'),skipped=r.get('skipped')))
        dump(out/'test_reports.json',reports)
        dump(out/'artifacts.json',[dict(path=p.relative_to(source).as_posix(),bytes=p.stat().st_size,sha256=sha(p)) for p in source.rglob('*.jar') if 'target' in p.parts])
        assert arm.resolve().is_relative_to((OUT/'caches').resolve());shutil.rmtree(arm)
    assert cache.resolve().is_relative_to((OUT/'caches').resolve());shutil.rmtree(cache)
if __name__=='__main__':main()
