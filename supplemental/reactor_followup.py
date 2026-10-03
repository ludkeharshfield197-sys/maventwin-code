from reactor_tests import *

def fetch_artifact(cache,g,a,v,typ='jar',origin='https://repo.maven.apache.org/maven2'):
    relative=g.replace('.','/')+'/'+a+'/'+v;folder=cache/relative;folder.mkdir(parents=True,exist_ok=True)
    for ext in ['pom']+(['jar'] if typ=='jar' else []):
        p=folder/f'{a}-{v}.{ext}'
        u=origin+'/'+relative+'/'+p.name
        if p.exists() and p.stat().st_size>0:b=p.read_bytes()
        else:
            with urllib.request.urlopen(u,timeout=30) as r:b=r.read()
        expected=None;remote_verified=False
        for attempt in range(3):
            try:
                with urllib.request.urlopen(u+'.sha1',timeout=15) as r:expected=r.read().decode().strip().split()[0]
                remote_verified=True;break
            except urllib.error.HTTPError:break
            except (urllib.error.URLError,TimeoutError):continue
        if expected is None and p.with_suffix(p.suffix+'.sha1').exists():expected=p.with_suffix(p.suffix+'.sha1').read_text().strip().split()[0]
        if expected:assert hashlib.sha1(b).hexdigest()==expected.lower()
        p.write_bytes(b)
        tracking=folder/'_remote.repositories'
        with tracking.open('a',encoding='utf-8') as f:f.write(p.name+'>central=\n')
        return_record={'url':u,'sha256':sha(p),'sha1_verified':expected is not None,'remote_sha1_fetched_in_this_materialization':remote_verified}
        with (cache/'materialization-downloads.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(return_record)+'\n')

def run(repo,area,props=(),repair=False):
    sid=repo.replace('/','__');base=OUT/area/sid;original=OUT/'sources'/sid
    seed=fresh_cache(area+'-'+sid,seed=OUT/'reactor_tests'/sid/'frozen_repository')
    if repair:
        log=(OUT/'reactor_tests'/sid/'runs/m3-r1/stdout.txt').read_text(encoding='utf-8')
        for attempt in range(5):
            missing=set(re.findall(r'artifact ([\w.]+):([\w.-]+):(jar|pom):([\w.-]+)',log))
            if not missing:break
            for g,a,typ,v in sorted(missing):fetch_artifact(seed,g,a,v,typ)
            src=OUT/'reactor_sources'/sid/f'{area}-repair-{attempt}';shutil.copytree(original,src,ignore=shutil.ignore_patterns('.git','target'),dirs_exist_ok=True)
            rec=maven('m3',Path(RT['jdk']),src,seed,base/f'materialization-{attempt}',['package','-DskipTests=false','-Dmaven.javadoc.skip=true']+list(props),recursive=True,timeout=180)
            if rec['exit_code']==0:break
            log=(base/f'materialization-{attempt}/stdout.txt').read_text(encoding='utf-8',errors='replace')
    frozen=base/'frozen_repository';shutil.copytree(seed,frozen);dump(base/'frozen_manifest.json',manifest(frozen))
    for rt,n in [('m3',1),('m4',1),('m4',2),('m3',2)]:
        src=OUT/'reactor_sources'/sid/f'{area}-{rt}-r{n}';shutil.copytree(original,src,ignore=shutil.ignore_patterns('.git','target'))
        cache=fresh_cache(f'{area}-{sid}-{rt}-{n}',seed=frozen);out=base/'runs'/f'{rt}-r{n}'
        maven(rt,Path(RT['jdk']),src,cache,out,['package','-DskipTests=false','-Dmaven.javadoc.skip=true']+list(props),timeout=240,recursive=True)
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
        tasks=[pool.submit(run,'google/gson','gson_targeted_tests',('-pl','gson,extras','-am')),pool.submit(run,'eclipse-ee4j/angus-activation','reactor_repaired',(),True)]
        for f in as_completed(tasks):f.result()
