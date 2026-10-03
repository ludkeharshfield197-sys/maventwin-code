"""Execute dependency APIs using each measured graph's resolved JAR set."""
from experiments import *
from reactor_followup import fetch_artifact

def nodes(tree):
    yield tree
    for child in tree.get('children',[]) or []:yield from nodes(child)

def main():
    base=OUT/'selected_dependency_execution_v2';classes=base/'classes';classes.mkdir(parents=True,exist_ok=True)
    repository=base/'resolved_repository'
    if not repository.exists():copy_tree(SEED,repository)
    process([str(Path(RT['jdk'])/'bin/javac.exe'),'-d',str(classes),str(CODE/'SelectedDependencyProbe.java')],CODE,base/'compile',60)
    rows=[]
    for repo,mode in [('apache/commons-compress','logging'),('spring-projects/spring-data-neo4j','netty')]:
        sid=repo.replace('/','__')
        for rt,n in [('m3',1),('m4',1),('m4',2),('m3',2)]:
            arm=base/sid/f'{rt}-r{n}';graph=OUT/'graph/jdk21'/sid/'baseline'/f'{rt}-r{n}/tree.json'
            selected=list(nodes(json.loads(graph.read_text(encoding='utf-8-sig'))))[1:]
            jars=[];missing=[]
            for x in selected:
                if x.get('type')=='pom':continue
                suffix='-'+x['classifier'] if x.get('classifier') else ''
                p=repository/x['groupId'].replace('.','/')/x['artifactId']/x['version']/(x['artifactId']+'-'+x['version']+suffix+'.jar')
                if not p.exists() and x['groupId'] in (['org.slf4j'] if mode=='logging' else ['io.netty','org.jctools']) and not suffix:
                    fetch_artifact(repository,x['groupId'],x['artifactId'],x['version'])
                if p.exists():jars.append(p)
                else:missing.append(str(p.relative_to(repository)))
            dump(arm/'selected_artifacts.json',dict(graph=str(graph),jars=[dict(path=str(p.relative_to(repository)),sha256=sha(p)) for p in jars],unmaterialized_nodes=missing))
            cp=os.pathsep.join(map(str,[classes]+list(dict.fromkeys(jars))))
            result=process([str(Path(RT['jdk'])/'bin/java.exe'),'-cp',cp,'SelectedDependencyProbe',mode],CODE,arm,60)
            lines=(arm/'stdout.txt').read_text(encoding='utf-8',errors='replace').splitlines()
            checks=[x for x in lines if x.startswith('CHECK ')]
            rows.append(dict(repo=repo,runtime=rt,repetition=n,exit_code=result['exit_code'],checks=';'.join(checks),origin=';'.join(x for x in lines if x.startswith('ORIGIN ')),jar_count=len(jars),unmaterialized_nodes=len(missing)))
    with (CODE/'SELECTED_DEPENDENCY_EXECUTION.csv').open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    summary={}
    for repo in sorted({x['repo'] for x in rows}):
        xs=[x for x in rows if x['repo']==repo]
        summary[repo]=dict(runs=len(xs),successful=sum(x['exit_code']==0 for x in xs),checks_per_run=[len(x['checks'].split(';')) for x in xs],checks_equal=len({x['checks'] for x in xs})==1,origins_differ=len({x['origin'] for x in xs})>1)
    dump(CODE/'SELECTED_DEPENDENCY_EXECUTION_SUMMARY.json',summary);print(json.dumps(summary,indent=2))

if __name__=='__main__':main()
