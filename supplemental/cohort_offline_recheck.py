"""Repeat all acquired snapshots from one artifact seed in ABBA order."""
from experiments import *

def one(row):
    sid=row['repo'].replace('/','__');base=OUT/'cohort_offline_recheck'/sid
    source=OUT/'cohort_offline_sources'/sid
    if not source.exists():copy_tree(ROOT/'final_evidence_v1/snapshots'/sid,source)
    caches={rt:OUT/'cohort_offline_caches'/sid/rt for rt in ['m3','m4']}
    for rt,cache in caches.items():
        if not cache.exists():copy_tree(SEED,cache)
    dump(base/'input.json',dict(repo=row['repo'],commit=row['commit'],resolution_target=row['resolution_target'],order=['m3-r1','m4-r1','m4-r2','m3-r2'],initial_seed_manifest='seed_manifest.json',goals=['effective-pom','dependency:tree','root validate'],source_kind='copied frozen POM snapshot'))
    for rt,n in [('m3',1),('m4',1),('m4',2),('m3',2)]:
        out=base/f'{rt}-r{n}'
        for layer in ['model','graph','validation']:
            folder=out/layer
            if (folder/'command.json').exists():continue
            if layer=='model':goals=['org.apache.maven.plugins:maven-help-plugin:3.5.1:effective-pom',f'-Doutput={folder}/effective-pom.xml']
            elif layer=='graph':goals=['-f',str(source/row['resolution_target']),'org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree','-DoutputType=json',f'-DoutputFile={folder}/tree.json']
            else:goals=['validate']
            maven(rt,Path(RT['jdk']),source,caches[rt],folder,goals,timeout=60)
    print('COHORT COMPLETE',sid,flush=True)

def main():
    rows=[x for x in read(ROOT/'final_evidence_v1/FINAL_PAPER_RESULTS.csv') if x['pom_complete']=='true']
    with ThreadPoolExecutor(max_workers=3) as pool:
        for job in as_completed([pool.submit(one,row) for row in rows]):job.result()

if __name__=='__main__':main()
