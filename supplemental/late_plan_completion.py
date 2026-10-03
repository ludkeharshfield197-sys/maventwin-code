from reactor_followup import fetch_artifact
from late_plans import *

def main():
    sid='oshi__oshi';base=OUT/'late_central_completed'/sid
    cache=fresh_cache('oshi-deploy-completed',seed=OUT/'late_central_materialized'/sid/'frozen_repository')
    src=ROOT/'final_evidence_v1/snapshots'/sid
    for rt in ['m3','m4']:
        for attempt in range(10):
            out=base/f'materialization-{rt}-{attempt}'
            maven(rt,Path(RT['jdk']),src,cache,out,['org.apache.maven.plugins:maven-help-plugin:3.5.1:effective-pom',f'-Doutput={out}/help-model.xml'],spy=True,spy_late=True,spy_phase='deploy',timeout=120)
            if (out/'observer/000-plan.tsv').exists():break
            log=(out/'observer/000-plan-error.txt').read_text(encoding='utf-8',errors='replace')
            missing=set(re.findall(r'artifact ([\w.-]+):([\w.-]+):(jar|pom):([\w.-]+)',log))
            if not missing:break
            for g,a,typ,v in sorted(missing):fetch_artifact(cache,g,a,v,typ)
    frozen=base/'frozen_repository';copy_tree(cache,frozen);dump(base/'frozen_manifest.json',manifest(frozen))
    dump(base/'input.json',{'repo':'oshi/oshi','source_path':str(src),'root_pom_sha256':sha(src/'pom.xml'),'planned_phase':'deploy','executed_goal':'maven-help-plugin:3.5.1:effective-pom','plan_stage':'afterSessionEnd'})
    for rt,n in [('m3',1),('m4',1),('m4',2),('m3',2)]:
        arm=fresh_cache(f'oshi-deploy-completed-{rt}-{n}',seed=frozen);out=base/'runs'/f'{rt}-r{n}'
        maven(rt,Path(RT['jdk']),src,arm,out,['org.apache.maven.plugins:maven-help-plugin:3.5.1:effective-pom',f'-Doutput={out}/help-model.xml'],spy=True,spy_late=True,spy_phase='deploy',timeout=120)
        assert arm.resolve().is_relative_to((OUT/'caches').resolve());shutil.rmtree(arm)
    assert cache.resolve().is_relative_to((OUT/'caches').resolve());shutil.rmtree(cache)
if __name__=='__main__':main()
