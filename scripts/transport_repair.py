"""Populate an experiment cache from the exact public release URL in a failed Maven transfer.
No substitutions, mirrors, version upgrades or snapshot guessing are allowed.
"""
from pathlib import Path
import urllib.request,urllib.parse,hashlib,re,json,datetime
def repair(log,cache,out):
    records=[]
    matches=re.findall(r'Could not transfer artifact ([\w.:-]+) from/to ([\w.-]+) \((https://[^)\s]+)\)',log)
    for coord,rid,base in dict.fromkeys(matches):
        bits=coord.split(':')
        if len(bits) not in [4,5]:continue
        group,artifact,typ=bits[:3];version=bits[-1];classifier=bits[3] if len(bits)==5 else ''
        if typ not in ['pom','jar'] or 'SNAPSHOT' in version:continue
        relative='/'.join([group.replace('.','/'),artifact,version,artifact+'-'+version+('-'+classifier if classifier else '')+'.'+typ])
        url=base.rstrip('/')+'/'+relative;target=cache/relative
        if target.exists():continue
        rec={'coordinate':coord,'repository_id':rid,'url':url,'utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
        try:
            def fetch(u):
                req=urllib.request.Request(u,headers={'User-Agent':'MavenTwin-metadata-pilot'})
                with urllib.request.urlopen(req,timeout=20) as f:
                    data=f.read(30_000_001)
                    if len(data)>30_000_000:raise ValueError('30 MB per repaired artifact cap')
                    return data
            data=fetch(url);checksum=fetch(url+'.sha1').decode().strip().split()[0]
            assert re.fullmatch('[0-9a-fA-F]{40}',checksum) and hashlib.sha1(data).hexdigest()==checksum.lower()
            target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
            target.with_name(target.name+'.sha1').write_text(checksum)
            marker=target.parent/'_remote.repositories'
            with marker.open('a',encoding='utf-8') as f:f.write('\n'+target.name+'>'+rid+'=\n')
            rec.update(status='VERIFIED_CANONICAL_RELEASE_CACHED',bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),sha1=checksum)
        except Exception as e:rec.update(status='REPAIR_FAILED',error=str(e))
        records.append(rec)
    (out/'canonical-transfer-repair.json').write_text(json.dumps(records,indent=2),encoding='utf-8')
    return records
