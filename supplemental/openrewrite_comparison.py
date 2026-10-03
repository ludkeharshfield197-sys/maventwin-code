"""Apply the official OpenRewrite Maven 4 recipe on isolated frozen project copies."""
from experiments import *
import experiments

def main():
    base=OUT/'openrewrite_comparison_v3';base.mkdir(exist_ok=True)
    settings=base/'settings.xml';settings.write_text('<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0"><mirrors><mirror><id>central</id><mirrorOf>central</mirrorOf><url>http://127.0.0.1:8766/</url></mirror></mirrors></settings>',encoding='utf-8')
    experiments.SETTINGS=settings
    cache=base/'repository'
    if not cache.exists():copy_tree(OUT/'openrewrite_comparison_v2/repository',cache)
    for repo in ['twilio/twilio-java','apache/curator','apache/commons-compress','spring-projects/spring-data-neo4j']:
        sid=repo.replace('/','__');case=base/sid;source=case/'source'
        if not source.exists():
            original=OUT/'sources'/sid
            if not original.exists():original=ROOT/'final_evidence_v1/snapshots'/sid
            copy_tree(original,source,ignore=shutil.ignore_patterns('.git','target'))
        before=[dict(path=str(p.relative_to(source)),sha256=sha(p)) for p in source.rglob('pom.xml')]
        goal='org.openrewrite.maven:rewrite-maven-plugin:6.46.1:runNoFork'
        props=['-Drewrite.activeRecipes=org.openrewrite.maven.MigrateToMaven4','-Drewrite.recipeArtifactCoordinates=org.openrewrite:rewrite-maven:8.90.4','-Drewrite.pomCacheEnabled=false','-Drewrite.exportDatatables=true']
        result=maven('m3',Path(RT['jdk']),source,cache,case/'recipe',['-U','-nsu',goal]+props,offline=False,timeout=600)
        after=[dict(path=str(p.relative_to(source)),sha256=sha(p)) for p in source.rglob('pom.xml')]
        dump(case/'result.json',dict(repo=repo,plugin_version='6.46.1',recipe_artifact='org.openrewrite:rewrite-maven:8.90.4',recipe='org.openrewrite.maven.MigrateToMaven4',before=before,after=after,command=result))
        if result['exit_code']==0:
            for n in [1,2]:maven('m4',Path(RT['jdk']),source,cache,case/f'post-m4-r{n}',['validate'],offline=False,timeout=90)
    print('OPENREWRITE COMPARISON COMPLETE',flush=True)

if __name__=='__main__':main()
