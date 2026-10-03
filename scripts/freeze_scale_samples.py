import csv, json
from harness import R, sha, utc, dump

old = json.loads((R/'samples'/'sample_lock.json').read_text())['samples']
old_repos = {x['repo'] for x in old}
eligible=[]
for p in sorted((R/'samples'/'scale_screening').glob('*/screening.json')):
    x=json.loads(p.read_text())
    if x.get('eligible') and x['repo'] not in old_repos:
        eligible.append(x)
by={k:[] for k in ['Apache','Eclipse','Spring','Independent']}
for x in sorted(eligible,key=lambda z:(z.get('selection_order',9999),z['repo'])):
    by.setdefault(x.get('stratum','Independent'),[]).append(x)
chosen = by['Apache'][:27] + by['Eclipse'][:14] + by['Spring'][:12] + by['Independent']
if len(chosen)!=86: raise SystemExit(f'expected 86 analyzable new rows, got {len(chosen)}')
chosen_repos={x['repo'] for x in chosen}
all_candidates=[]
for f in [R/'samples'/'scale_candidate_seed.json',R/'samples'/'scale_candidate_extra.json',R/'samples'/'scale_candidate_extra2.json',R/'samples'/'scale_candidate_extra3.json']:
    if f.exists(): all_candidates += json.loads(f.read_text())
unknown=[]
for repo in all_candidates:
    org=repo.split('/')[0]
    if repo in old_repos or repo in chosen_repos or repo in {x['repo'] for x in unknown}: continue
    if org.lower() in {'apache','eclipse','eclipse-ee4j','spring-projects','spring-io'}: continue
    unknown.append({'repo':repo,'org':org,'stratum':'Independent','id':repo.replace('/','__'),'commit':'UNKNOWN_REMOTE_HEAD','commit_date':'UNKNOWN','source_path':'','pom':'pom.xml','packaging':'UNKNOWN','module_count':'','stars':0,'acquisition_status':'UNKNOWN','exclusion':'REMOTE_HEAD_UNAVAILABLE_OR_TIMEOUT_BEFORE_FREEZE'})
    if len(unknown)>=34: break
if len(unknown)!=34: raise SystemExit(f'expected 34 unknown rows, got {len(unknown)}')
rows=[]
for x in old:
    rows.append({'id':x['id'],'repo':x['repo'],'stratum':x['stratum'],'commit':x['commit'],'commit_date':x['commit_date'],'source_path':str(R/'samples'/'sources'/x['id']),'pom':x.get('pom','pom.xml'),'packaging':x.get('packaging','jar'),'module_count':len(x.get('modules',[])),'stars':x.get('stars',0),'analyzable':'true','acquisition_status':'ELIGIBLE'})
for x in chosen:
    rows.append({'id':x['id'],'repo':x['repo'],'stratum':x['stratum'],'commit':x['commit'],'commit_date':x['commit_date'],'source_path':x['source_path'],'pom':x.get('pom','pom.xml'),'packaging':x.get('packaging','jar'),'module_count':len(x.get('modules',[])),'stars':x.get('stars',0),'analyzable':'true','acquisition_status':'ELIGIBLE'})
for x in unknown:
    rows.append(x|{'analyzable':'false'})
if len(rows)!=150 or len({x['repo'] for x in rows})!=150: raise SystemExit('row count or duplicate check failed')
fields=['id','repo','stratum','commit','commit_date','source_path','pom','packaging','module_count','stars','analyzable','acquisition_status']
out=R/'samples'/'scale_samples.csv'
with out.open('w',newline='',encoding='utf-8') as f:
    w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows({k:x.get(k,'') for k in fields} for x in rows)
lock={'frozen_utc':utc(),'samples_csv_sha256':sha(out),'total':150,'analyzable_pre_scale':116,'unknown_pre_scale':34,'m4_runs_before_lock':0,'selection_rule':'27 Apache + 14 Eclipse + 12 Spring + all 33 eligible Independent new rows; 34 Independent remote acquisition failures retained as UNKNOWN','samples':rows}
dump(R/'samples'/'scale_sample_lock.json',lock)
print(json.dumps({'total':150,'analyzable':116,'unknown':34,'sha256':lock['samples_csv_sha256']},ensure_ascii=False))
