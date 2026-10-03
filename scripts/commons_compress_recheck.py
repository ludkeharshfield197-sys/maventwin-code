import json,shutil
from harness import R,dump
src=R/'metadata_diff'/'apache__commons-compress'; out=R/'commons_compress_recheck';out.mkdir(exist_ok=True)
observations=[]
for rt in ['m3','m4']:
  for rep in [1,2]:
    p=src/f'{rt}-r{rep}'/'mediation'/'mediation-evidence.json'; data=json.loads(p.read_text()) if p.exists() else []
    hit=[x for x in data if x.get('groupId')=='org.slf4j' and x.get('artifactId')=='jcl-over-slf4j' and x.get('state') in ['INCLUDED','OMITTED_CONFLICT','OMITTED_DUPLICATE']]
    observations.append({'runtime':rt,'repeat':rep,'artifact_identity':'org.slf4j:jcl-over-slf4j:jar','matches':hit,'raw_evidence':str(p.relative_to(R))})
result={'classification':'UNKNOWN','observations':observations}
m3=[x for x in observations if x['runtime']=='m3'];m4=[x for x in observations if x['runtime']=='m4']
def selected(x): return next((y for y in x['matches'] if y.get('state')=='INCLUDED'),None)
if all(selected(x) for x in observations):
  v3={selected(x)['version'] for x in m3};v4={selected(x)['version'] for x in m4}
  scopes={selected(x).get('scope') for x in observations}; paths={tuple(selected(x).get('parent_path',[])) for x in observations}
  result.update(classification='CONFIRMED' if len(v3)==len(v4)==1 and v3!=v4 and len(scopes)==1 and len(paths)==1 else 'NOT_REPRODUCED',m3_version=sorted(v3),m4_version=sorted(v4),scope=sorted(scopes),dependency_path=sorted(paths)[0] if paths else [])
dump(out/'COMMONS_COMPRESS_RECHECK.json',result)
for rt in ['m3','m4']:
  for rep in [1,2]: shutil.copytree(src/f'{rt}-r{rep}',out/f'{rt}-r{rep}',dirs_exist_ok=True)
print(json.dumps({'classification':result['classification'],'m3_version':result.get('m3_version'),'m4_version':result.get('m4_version')}))
