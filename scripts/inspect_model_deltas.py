import os  # Configurable workspace; no machine-specific paths.
import csv,json,collections
from pathlib import Path
R=(Path(os.environ.get("MAVENTWIN_WORKSPACE", Path(__file__).resolve().parents[1])).resolve()); rows=list(csv.DictReader((R/'metrics'/'FINAL_REPOSITORY_RESULTS.csv').open(encoding='utf-8'))); counts=collections.Counter(); sample=[]
for r in rows:
 if r['analyzable']!='true':continue
 sid=r['repo'].replace('/','__')
 a=json.loads((R/'scale_runs'/sid/'m3-r1'/'normalized.json').read_text()).get('model_normalized') or []
 b=json.loads((R/'scale_runs'/sid/'m4-r1'/'normalized.json').read_text()).get('model_normalized') or []
 da={x['tag']:x for x in a};db={x['tag']:x for x in b};diff=[k for k in sorted(da.keys()|db.keys()) if da.get(k)!=db.get(k)]
 counts.update(diff)
 if diff and len(sample)<40:sample.append({'repo':r['repo'],'diff_sections':diff,'m3':{k:da.get(k) for k in diff},'m4':{k:db.get(k) for k in diff}})
(R/'metrics'/'MODEL_DELTA_REVIEW.json').write_text(json.dumps({'section_counts':counts,'examples':sample},ensure_ascii=False,indent=2),encoding='utf-8')
print(counts);print([(x['repo'],x['diff_sections']) for x in sample])
