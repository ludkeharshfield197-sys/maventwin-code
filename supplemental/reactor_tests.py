from experiments import *

def one(repo):
    sid=repo.replace('/','__');original=full_source(repo)
    if original is None:dump(OUT/'reactor_tests'/sid/'unavailable.json',{'status':'SOURCE_UNAVAILABLE'});return
    seed=fresh_cache('reactor-warm-'+sid)
    base=OUT/'reactor_tests'/sid
    for rt in ['m3','m4']:
        src=OUT/'reactor_sources'/sid/('warm-'+rt)
        shutil.copytree(original,src,ignore=shutil.ignore_patterns('.git','target'))
        maven(rt,Path(RT['jdk']),src,seed,base/('warm-'+rt),['package','-DskipTests=false','-Dmaven.javadoc.skip=true'],offline=False,timeout=300,recursive=True)
    frozen=base/'frozen_repository';shutil.copytree(seed,frozen);dump(base/'frozen_repository_manifest.json',manifest(frozen))
    for rt,n in [('m3',1),('m4',1),('m4',2),('m3',2)]:
        src=OUT/'reactor_sources'/sid/f'{rt}-r{n}';shutil.copytree(original,src,ignore=shutil.ignore_patterns('.git','target'))
        cache=fresh_cache(f'reactor-{sid}-{rt}-{n}',seed=frozen);out=base/'runs'/f'{rt}-r{n}'
        maven(rt,Path(RT['jdk']),src,cache,out,['package','-DskipTests=false','-Dmaven.javadoc.skip=true'],timeout=300,recursive=True)
        reports=[]
        for p in src.rglob('TEST-*.xml'):
            try:
                r=ET.parse(p).getroot();reports.append(dict(path=p.relative_to(src).as_posix(),tests=r.get('tests'),failures=r.get('failures'),errors=r.get('errors'),skipped=r.get('skipped')))
            except ET.ParseError:pass
        dump(out/'test_reports.json',reports)
        artifacts=[dict(path=p.relative_to(src).as_posix(),bytes=p.stat().st_size,sha256=sha(p)) for p in src.rglob('*.jar') if 'target' in p.parts]
        dump(out/'artifacts.json',artifacts)
        assert cache.resolve().is_relative_to((OUT/'caches').resolve());shutil.rmtree(cache)
    assert seed.resolve().is_relative_to((OUT/'caches').resolve());shutil.rmtree(seed)

if __name__=='__main__':
    with ThreadPoolExecutor(max_workers=2) as pool:
        for f in as_completed([pool.submit(one,r) for r in ['google/gson','eclipse-ee4j/angus-activation']]):f.result()
