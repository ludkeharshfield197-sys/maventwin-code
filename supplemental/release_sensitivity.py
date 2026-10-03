from experiments import *
def run():
    tools=OUT/'tools';tools.mkdir(exist_ok=True)
    url='https://dlcdn.apache.org/maven/maven-3/3.10.0/binaries/apache-maven-3.10.0-bin.zip';checkurl='https://downloads.apache.org/maven/maven-3/3.10.0/binaries/apache-maven-3.10.0-bin.zip.sha512';archive=tools/'apache-maven-3.10.0-bin.zip'
    def fetch(u):
        with urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'MavenTwin-revision'}),timeout=35) as r:return r.read()
    b=fetch(url);expected=fetch(checkurl).decode().strip().split()[0]
    assert hashlib.sha512(b).hexdigest()==expected.lower();archive.write_bytes(b)
    with zipfile.ZipFile(archive) as z:z.extractall(tools)
    RT['m310']=str(tools/'apache-maven-3.10.0')
    dump(tools/'maven310_distribution.json',{'url':url,'checksum_url':checkurl,'sha512':expected,'downloaded_utc':datetime.now(timezone.utc).isoformat(),'maven4_latest_checked':'The official download page still lists rc-7 as Maven 4 preview.'})
    for repo in ['apache/commons-compress','spring-projects/spring-data-neo4j','apache/curator','twilio/twilio-java']:
        sid=repo.replace('/','__');src=(ROOT/'final_evidence_v1/snapshots'/sid) if 'commons-compress' in repo or 'neo4j' in repo else (OUT/'sources'/sid)
        cache=fresh_cache('m310-'+sid)
        for n in [1,2]:
            out=OUT/'release_sensitivity'/sid/f'm310-r{n}';out.mkdir(parents=True,exist_ok=True)
            goals=['org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree','-DoutputType=json',f'-DoutputFile={out}/tree.json'] if 'commons-compress' in repo or 'neo4j' in repo else ['validate']
            maven('m310',Path(RT['jdk']),src,cache,out,goals)
        assert cache.resolve().is_relative_to((OUT/'caches').resolve());shutil.rmtree(cache)
if __name__=='__main__':run()
