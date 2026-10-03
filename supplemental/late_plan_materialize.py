from reactor_followup import fetch_artifact
from late_plans import *

def main():
    sid='oshi__oshi';base=OUT/'late_central_materialized'/sid
    cache=fresh_cache('oshi-deploy-materialized',seed=OUT/'late_central_plans'/sid/'frozen_repository')
    fetch_artifact(cache,'org.codehaus.mojo','build-helper-maven-plugin','3.6.2')
    frozen=base/'frozen_repository';copy_tree(cache,frozen);dump(base/'frozen_manifest.json',manifest(frozen))
    src=ROOT/'final_evidence_v1/snapshots'/sid
    dump(base/'input.json',{'repo':'oshi/oshi','source_path':str(src),'root_pom_sha256':sha(src/'pom.xml'),'planned_phase':'deploy','executed_goal':'maven-help-plugin:3.5.1:effective-pom','plan_stage':'afterSessionEnd','materialized_plugin':'org.codehaus.mojo:build-helper-maven-plugin:3.6.2'})
    for rt,n in [('m3',1),('m4',1),('m4',2),('m3',2)]:
        arm=fresh_cache(f'oshi-late-materialized-{rt}-{n}',seed=frozen);out=base/'runs'/f'{rt}-r{n}'
        maven(rt,Path(RT['jdk']),src,arm,out,['org.apache.maven.plugins:maven-help-plugin:3.5.1:effective-pom',f'-Doutput={out}/help-model.xml'],spy=True,spy_late=True,spy_phase='deploy',timeout=120)
        assert arm.resolve().is_relative_to((OUT/'caches').resolve());shutil.rmtree(arm)
    assert cache.resolve().is_relative_to((OUT/'caches').resolve());shutil.rmtree(cache)
if __name__=='__main__':main()
