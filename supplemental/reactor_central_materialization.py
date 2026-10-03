from reactor_followup import *

sid='eclipse-ee4j__angus-activation';area='reactor_central_materialized';base=OUT/area/sid
seed=fresh_cache(area,seed=OUT/'reactor_materialized'/sid/'frozen_repository')
changes=[]
for p in seed.rglob('_remote.repositories'):
    text=p.read_text(encoding='utf-8');extra=[]
    for filename in re.findall(r'^([^\r\n=]+)>central-[0-9a-f]+=\s*$',text,re.M):
        target=p.parent/filename;check=target.with_suffix(target.suffix+'.sha1')
        if not target.exists() or not check.exists():continue
        assert hashlib.sha1(target.read_bytes()).hexdigest()==check.read_text().strip().split()[0].lower()
        line=filename+'>central='
        if line not in text:extra.append(line)
    if extra:p.write_text(text+'\n'.join(extra)+'\n',encoding='utf-8');changes.append({'path':p.relative_to(seed).as_posix(),'canonical_central_entries_added':extra})
dump(base/'repository_identity_materialization.json',{'changes':changes,'binary_or_pom_bytes_changed':False,'rule':'Associate checksum-verified artifacts tracked from the canonical Central URL under a hash-suffixed runtime repository ID with the canonical central ID.'})
frozen=base/'frozen_repository';copy_tree(seed,frozen,dirs_exist_ok=True);dump(base/'frozen_manifest.json',manifest(frozen))
original=OUT/'sources'/sid
for rt,n in [('m3',1),('m4',1),('m4',2),('m3',2)]:
    src=OUT/'reactor_sources'/sid/f'{area}-{rt}-r{n}';shutil.copytree(original,src,ignore=shutil.ignore_patterns('.git','target'))
    cache=fresh_cache(f'{area}-{rt}-{n}',seed=frozen);out=base/'runs'/f'{rt}-r{n}'
    maven(rt,Path(RT['jdk']),src,cache,out,['package','-DskipTests=false','-Dmaven.javadoc.skip=true'],timeout=240,recursive=True)
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
