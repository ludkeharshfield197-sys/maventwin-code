from experiments import *
def source_copy(repo,name):
    sid=repo.replace('/','__');dst=OUT/'apply_cases'/sid/name
    if dst.exists():return dst
    src=OUT/'sources'/sid
    if not src.exists():src=ROOT/'final_evidence_v1/snapshots'/sid
    shutil.copytree(src,dst,ignore=shutil.ignore_patterns('.git','target'))
    return dst
def run():
    # Four concrete observed cases; source edits are confined to copies.
    for repo in ['twilio/twilio-java','apache/curator','apache/commons-compress','spring-projects/spring-data-neo4j']:
        sid=repo.replace('/','__');src=source_copy(repo,'mvnup')
        before=manifest(src);cache=fresh_cache('apply-'+sid)
        rec=maven('m4',Path(RT['jdk']),src,cache,OUT/'apply_cases'/sid/'apply-log',['apply','--model-version','4.0.0'],offline=False,timeout=120,up=True)
        after=manifest(src);dump(OUT/'apply_cases'/sid/'edit_manifest.json',{'before':before,'after':after,'apply_result':rec})
        for rt,n in [('m3',1),('m4',1),('m4',2),('m3',2)]:
            out=OUT/'apply_cases'/sid/'post'/f'{rt}-r{n}';out.mkdir(parents=True,exist_ok=True)
            goals=['validate'] if repo in ['twilio/twilio-java','apache/curator'] else ['org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree','-DoutputType=json',f'-DoutputFile={out}/tree.json']
            maven(rt,Path(RT['jdk']),src,cache,out,goals,offline=False,timeout=120)
        assert cache.resolve().is_relative_to((OUT/'caches').resolve());shutil.rmtree(cache)
    # Demonstrate the diagnostic-guided repair independently of migration tooling.
    src=source_copy('twilio/twilio-java','diagnostic-repair');pom=src/'pom.xml'
    text=pom.read_text(encoding='utf-8');matches=list(re.finditer(r'<plugin>\s*(?:<groupId>org\.apache\.maven\.plugins</groupId>\s*)?<artifactId>maven-surefire-plugin</artifactId>.*?</plugin>',text,re.S))
    assert len(matches)>=2, 'Expected two frozen Surefire declarations'
    victim=matches[-1];pom.write_text(text[:victim.start()]+text[victim.end():],encoding='utf-8')
    dump(OUT/'apply_cases/twilio__twilio-java/diagnostic_repair.json',{'removed_span':[victim.start(),victim.end()],'removed_xml':victim.group(),'before_sha256':hashlib.sha256(text.encode()).hexdigest(),'after_sha256':sha(pom),'intervention':'Remove the second active maven-surefire-plugin declaration in the isolated source copy.'})
    cache=fresh_cache('twilio-diagnostic-repair')
    for rt,n in [('m3',1),('m4',1),('m4',2),('m3',2)]:maven(rt,Path(RT['jdk']),src,cache,OUT/'apply_cases/twilio__twilio-java/repair-post'/f'{rt}-r{n}',['validate'],offline=False,timeout=120)
if __name__=='__main__':run()
