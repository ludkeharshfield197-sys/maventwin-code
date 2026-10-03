from plan_recheck import *

def late_one(repo,phase,area):
    sid=repo.replace('/','__');src=ROOT/'final_evidence_v1/snapshots'/sid
    if not (src/'pom.xml').exists():
        row=next((r for r in read(ROOT/'samples/scale_samples.csv') if r['id']==sid),None)
        src=Path(row['source_path']) if row else ROOT/'samples/sources'/sid
    if not (src/'pom.xml').exists():dump(OUT/area/sid/'unavailable.json',{'status':'SOURCE_UNAVAILABLE','repo':repo});return
    base=OUT/area/sid;frozen=base/'frozen_repository'
    if not (base/'frozen_manifest.json').exists():
        prior=OUT/'plan_recheck'/sid/'frozen_plan_repository'
        cache=fresh_cache(area+'-warm-'+sid,seed=prior if prior.exists() else SEED)
        for rt in ['m3','m4']:
            maven(rt,Path(RT['jdk']),src,cache,base/('warm-'+rt),['org.apache.maven.plugins:maven-help-plugin:3.5.1:effective-pom',f'-Doutput={base}/warm-{rt}/help-model.xml'],spy=True,spy_late=True,spy_phase=phase,offline=False,timeout=120)
        copy_tree(cache,frozen,dirs_exist_ok=True);dump(base/'frozen_manifest.json',manifest(frozen))
        assert cache.resolve().is_relative_to((OUT/'caches').resolve());shutil.rmtree(cache)
    dump(base/'input.json',{'repo':repo,'source_path':str(src),'root_pom_sha256':sha(src/'pom.xml'),'planned_phase':phase,'executed_goal':'maven-help-plugin:3.5.1:effective-pom','plan_stage':'afterSessionEnd, after all afterProjectsRead callbacks'})
    for rt,n in [('m3',1),('m4',1),('m4',2),('m3',2)]:
        out=base/'runs'/f'{rt}-r{n}'
        if (out/'command.json').exists():continue
        arm=fresh_cache(f'{area}-{sid}-{rt}-{n}',seed=frozen)
        maven(rt,Path(RT['jdk']),src,arm,out,['org.apache.maven.plugins:maven-help-plugin:3.5.1:effective-pom',f'-Doutput={out}/help-model.xml'],spy=True,spy_late=True,spy_phase=phase,timeout=100)
        assert arm.resolve().is_relative_to((OUT/'caches').resolve());shutil.rmtree(arm)

if __name__=='__main__':
    cases=json.loads((OUT/'instrument/selected_cases.json').read_text())
    central=json.loads((ROOT/'metrics/extension-binding-cases.json').read_text())
    tasks=[(repo,'package','late_package_plans') for group,repo in cases]+[(x['id'].replace('__','/'),'deploy','late_central_plans') for x in central]
    with ThreadPoolExecutor(max_workers=3) as pool:
        for f in as_completed([pool.submit(late_one,*t) for t in tasks]):f.result()
