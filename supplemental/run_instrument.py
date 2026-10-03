from experiments import *
def run():
    prov=read(ROOT/'artifacts/reviewer_revision/model/model_delta_summary.csv');chosen=[]
    for group in ['source','runtime','unresolved']:
        candidates=[x for x in prov if (x['project_pom_evidence']=='true' if group=='source' else (x['runtime_only_evidence']=='true' if group=='runtime' else x['project_pom_evidence']!='true' and x['runtime_only_evidence']!='true'))]
        for x in sorted(candidates,key=lambda x:x['repo'])[:4]:chosen.append((group,x['repo']))
    dump(OUT/'instrument/selected_cases.json',chosen)
    for group,repo in chosen:
        sid=repo.replace('/','__');src=ROOT/'final_evidence_v1/snapshots'/sid
        caches={rt:fresh_cache(f'instrument-{sid}-{rt}') for rt in ['m3','m4']}
        for rt,n in [('m3',1),('m4',1),('m4',2),('m3',2)]:
            out=OUT/'instrument/runs'/sid/f'{rt}-r{n}';out.mkdir(parents=True,exist_ok=True)
            maven(rt,Path(RT['jdk']),src,caches[rt],out,['org.apache.maven.plugins:maven-help-plugin:3.5.1:effective-pom',f'-Doutput={out}/help-model.xml'],spy=True,timeout=100)
        for c in caches.values():
            assert c.resolve().is_relative_to((OUT/'caches').resolve());shutil.rmtree(c)
    print('INSTRUMENT_COMPLETE',flush=True)
if __name__=='__main__':run()
