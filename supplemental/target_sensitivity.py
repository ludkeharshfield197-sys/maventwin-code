from experiments import *
def one(repo,targets):
    sid=repo.replace('/','__');src=ROOT/'final_evidence_v1/snapshots'/sid
    caches={rt:fresh_cache(f'target-{sid}-{rt}') for rt in ['m3','m4']}
    for i,target in enumerate(targets):
        for rt,n in [('m3',1),('m4',1),('m4',2),('m3',2)]:
            out=OUT/'targets'/sid/f'target-{i}'/f'{rt}-r{n}';out.mkdir(parents=True,exist_ok=True)
            maven(rt,Path(RT['jdk']),src,caches[rt],out,['-f',str(src/target),'org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree','-DoutputType=json',f'-DoutputFile={out}/tree.json'],timeout=60)
    for c in caches.values():
        assert c.resolve().is_relative_to((OUT/'caches').resolve());shutil.rmtree(c)
def run():
    paper=read(ROOT/'final_evidence_v1/FINAL_PAPER_RESULTS.csv');samples={r['repo']:r for r in read(ROOT/'samples/scale_samples.csv')};chosen=[]
    for group in ['Apache','Eclipse','Spring','Independent']:
        candidates=[]
        for row in paper:
            if samples[row['repo']]['stratum']!=group or row['resolution_comparable']!='RESOLUTION_COMPARABLE':continue
            sid=row['repo'].replace('/','__');src=ROOT/'final_evidence_v1/snapshots'/sid
            others=[]
            for p in sorted(src.rglob('pom.xml')):
                rel=p.relative_to(src).as_posix()
                if rel==row['resolution_target']:continue
                try:
                    r=ET.parse(p).getroot()
                    if r.findtext('m:packaging','jar',NS)!='pom' and r.findall('m:dependencies/m:dependency',NS):others.append(rel)
                except Exception:continue
            if others:candidates.append((row['repo'],[row['resolution_target']]+others[:2]))
        chosen+=sorted(candidates)[:2]
    dump(OUT/'targets/selection.json',{'policy':'First two lexicographic comparable repositories per stratum with alternate non-pom dependency-bearing POM; original target plus up to two alternate POMs.','cases':chosen})
    with ThreadPoolExecutor(max_workers=2) as pool:
        for f in as_completed([pool.submit(one,*c) for c in chosen]):f.result()
if __name__=='__main__':run()
