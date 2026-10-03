"""Compare official recipe application on complete frozen Git checkouts."""
from experiments import *
import experiments

def main():
    base=OUT/'openrewrite_full_checkouts';base.mkdir(exist_ok=True)
    settings=base/'settings.xml';settings.write_text('<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0"><mirrors><mirror><id>central</id><mirrorOf>central</mirrorOf><url>http://127.0.0.1:8766/</url></mirror></mirrors></settings>',encoding='utf-8')
    experiments.SETTINGS=settings;cache=base/'repository'
    if not cache.exists():copy_tree(OUT/'openrewrite_comparison_v3/repository',cache)
    for repo in ['twilio/twilio-java','apache/curator','apache/commons-compress','spring-projects/spring-data-neo4j']:
        original=full_source(repo);sid=repo.replace('/','__');case=base/sid;source=case/'source'
        row=next(x for x in read(ROOT/'samples/scale_samples.csv') if x['repo']==repo)
        if original is None:
            dump(case/'source_unavailable.json',dict(repo=repo,commit=row['commit']));continue
        if not (source/'.git').exists():
            case.mkdir(exist_ok=True)
            r=process(['git','-c','safe.directory=*','-c','core.longpaths=true','clone','--shared','--no-checkout',str(original),str(source)],ROOT,case/'clone',90)
            if r['exit_code']!=0:continue
            r=process(['git','-c','safe.directory=*','-c','core.longpaths=true','-C',str(source),'checkout','--detach',row['commit']],ROOT,case/'checkout',120)
            if r['exit_code']!=0:continue
        before=[dict(path=str(p.relative_to(source)),sha256=sha(p)) for p in source.rglob('pom.xml') if 'target' not in p.parts]
        for rt,n in [('m3',1),('m4',1),('m4',2),('m3',2)]:
            maven(rt,Path(RT['jdk']),source,cache,case/f'pre-{rt}-r{n}',['validate'],offline=True,timeout=180)
        goal='org.openrewrite.maven:rewrite-maven-plugin:6.46.1:runNoFork'
        result=maven('m3',Path(RT['jdk']),source,cache,case/'recipe',['-U','-nsu',goal,'-Drewrite.activeRecipes=org.openrewrite.maven.MigrateToMaven4','-Drewrite.recipeArtifactCoordinates=org.openrewrite:rewrite-maven:8.90.4','-Drewrite.pomCacheEnabled=false','-Drewrite.exportDatatables=true'],offline=False,timeout=600)
        after=[dict(path=str(p.relative_to(source)),sha256=sha(p)) for p in source.rglob('pom.xml') if 'target' not in p.parts]
        dump(case/'result.json',dict(repo=repo,commit=row['commit'],source_kind='complete Git checkout at frozen commit',plugin_version='6.46.1',recipe_artifact='org.openrewrite:rewrite-maven:8.90.4',recipe='org.openrewrite.maven.MigrateToMaven4',before=before,after=after,command=result))
        if result['exit_code']==0:
            for n in [1,2]:maven('m4',Path(RT['jdk']),source,cache,case/f'post-offline-m4-r{n}',['validate'],offline=True,timeout=180)
    dump(base/'repository_manifest.json',manifest(cache));print('FULL CHECKOUT RECIPE COMPARISON COMPLETE',flush=True)

if __name__=='__main__':main()
