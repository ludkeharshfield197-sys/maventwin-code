from experiments import *

def one(repo,phase='package',area='plan_recheck'):
    sid=repo.replace('/','__');src=ROOT/'final_evidence_v1/snapshots'/sid
    if not (src/'pom.xml').exists():
        row=next((r for r in read(ROOT/'samples/scale_samples.csv') if r['id']==sid),None)
        src=Path(row['source_path']) if row else ROOT/'samples/sources'/sid
    if not (src/'pom.xml').exists():
        dump(OUT/area/sid/'unavailable.json',{'repo':repo,'status':'SOURCE_UNAVAILABLE'});return
    # Warm only a copied repository, then freeze its byte content before the paired offline measurements.
    cache=fresh_cache(area+'-warm-'+sid)
    base=OUT/area/sid
    for rt in ['m3','m4']:
        maven(rt,Path(RT['jdk']),src,cache,base/('warm-'+rt),['org.apache.maven.plugins:maven-help-plugin:3.5.1:effective-pom',f'-Doutput={base}/warm-{rt}/help-model.xml'],spy=True,spy_phase=phase,offline=False,timeout=120)
    frozen=base/'frozen_plan_repository';shutil.copytree(cache,frozen)
    dump(base/'frozen_plan_manifest.json',manifest(frozen))
    for rt,n in [('m3',1),('m4',1),('m4',2),('m3',2)]:
        out=base/'runs'/f'{rt}-r{n}'
        arm=fresh_cache(f'{area}-{sid}-{rt}-{n}',seed=frozen)
        maven(rt,Path(RT['jdk']),src,arm,out,['org.apache.maven.plugins:maven-help-plugin:3.5.1:effective-pom',f'-Doutput={out}/help-model.xml'],spy=True,spy_phase=phase,timeout=100)
        assert arm.resolve().is_relative_to((OUT/'caches').resolve());shutil.rmtree(arm)
    assert cache.resolve().is_relative_to((OUT/'caches').resolve());shutil.rmtree(cache)

def run():
    one('apache/avro')
    cases=json.loads((ROOT/'metrics/extension-binding-cases.json').read_text())
    with ThreadPoolExecutor(max_workers=2) as pool:
        for f in as_completed([pool.submit(one,x['id'].replace('__','/'), 'deploy','central_plans') for x in cases]):f.result()

if __name__=='__main__':run()
