"""Retry incomplete recipe applications after artifact materialization."""
from experiments import *
import experiments

def main():
    base=OUT/'openrewrite_comparison_v3';experiments.SETTINGS=base/'settings.xml';cache=base/'repository'
    for p in sorted(base.glob('*/result.json')):
        obj=json.loads(p.read_text());case=p.parent;source=case/'source'
        if obj['command']['exit_code']==0:continue
        shutil.copy2(p,case/'result-initial.json')
        goal='org.openrewrite.maven:rewrite-maven-plugin:6.46.1:runNoFork'
        result=maven('m3',Path(RT['jdk']),source,cache,case/'recipe-retry',['-U','-nsu',goal,'-Drewrite.activeRecipes=org.openrewrite.maven.MigrateToMaven4','-Drewrite.recipeArtifactCoordinates=org.openrewrite:rewrite-maven:8.90.4','-Drewrite.pomCacheEnabled=false','-Drewrite.exportDatatables=true'],offline=False,timeout=600)
        obj['initial_command']=obj['command'];obj['command']=result;obj['recipe_output']='recipe-retry'
        obj['after']=[dict(path=str(x.relative_to(source)),sha256=sha(x)) for x in source.rglob('pom.xml')]
        dump(p,obj)
        if result['exit_code']==0:
            for n in [1,2]:maven('m4',Path(RT['jdk']),source,cache,case/f'post-m4-r{n}',['validate'],offline=True,timeout=180)
    print('RECIPE RETRY COMPLETE',flush=True)

if __name__=='__main__':main()
