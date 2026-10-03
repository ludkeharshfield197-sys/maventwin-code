from experiments import *
def run():
    cases=[('pax-exam','org.ops4j.pax.exam','pax-exam-link-mvn','4.13.5','test'),('neo4j-driver','org.neo4j.driver','neo4j-java-driver','6.2.1','compile')]
    for name,g,a,v,scope in cases:
        src=OUT/'minimal_graphs'/name/'project';src.mkdir(parents=True,exist_ok=True)
        (src/'pom.xml').write_text(f'<project xmlns="http://maven.apache.org/POM/4.0.0"><modelVersion>4.0.0</modelVersion><groupId>org.maventwin.controls</groupId><artifactId>{name}</artifactId><version>1.0</version><dependencies><dependency><groupId>{g}</groupId><artifactId>{a}</artifactId><version>{v}</version><scope>{scope}</scope></dependency></dependencies></project>',encoding='utf-8')
        for variant,props in [('default',[]),('transitivity_false',['-Dmaven.resolver.dependencyManagerTransitivity=false'])]:
            caches={rt:fresh_cache(f'minimal-{name}-{variant}-{rt}') for rt in ['m3','m4']}
            for rt,n in [('m3',1),('m4',1),('m4',2),('m3',2)]:
                out=OUT/'minimal_graphs'/name/variant/f'{rt}-r{n}';out.mkdir(parents=True,exist_ok=True)
                maven(rt,Path(RT['jdk']),src,caches[rt],out,['org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree','-DoutputType=json',f'-DoutputFile={out}/tree.json'],props if rt=='m4' else [])
            for c in caches.values():
                assert c.resolve().is_relative_to((OUT/'caches').resolve());shutil.rmtree(c)
if __name__=='__main__':run()
