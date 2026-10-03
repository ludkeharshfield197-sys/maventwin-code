import csv,json
from run_scale_experiment import R,ROOT
samples=list(csv.DictReader((R/'samples'/'scale_samples.csv').open(encoding='utf-8')))
def load(sid,rt,rep):
 p=ROOT/sid/f'{rt}-r{rep}'/'normalized.json'
 return json.loads(p.read_text()) if p.exists() else {'command':{'exit_code':None}}
def graph_keys(x):
 return {(z.get('groupId'),z.get('artifactId'),z.get('version'),z.get('scope'),z.get('path')) for z in (x or [])}
rows=[]
for s in samples:
 if s['analyzable'].lower()!='true':
  rows.append({'repo':s['repo'],'commit':s['commit'],'analyzable':'false','model_divergence':'UNKNOWN','resolution_divergence':'UNKNOWN','execution_divergence':'UNKNOWN','validation_status':'UNKNOWN','meaningful_divergence':'false','root_cause':'UNKNOWN','mvnup_relation':'NOT_APPLICABLE','manually_checked':'false','notes':'UNKNOWN acquisition'}); continue
 a=[load(s['id'],'m3',r) for r in [1,2]]; b=[load(s['id'],'m4',r) for r in [1,2]]
 ma=a[0].get('model_normalized'); mb=b[0].get('model_normalized'); model=ma!=mb; mm=model and any(k in json.dumps([ma,mb],sort_keys=True) for k in ['dependencies','dependencyManagement','plugins','executions','profiles','modules','properties'])
 ga=[graph_keys(x.get('dependency_graph')) for x in a]; gb=[graph_keys(x.get('dependency_graph')) for x in b]; resolution=ga[0]!=gb[0] and ga[0]==ga[1] and gb[0]==gb[1]
 pa=a[0].get('execution_plan'); pb=b[0].get('execution_plan'); execution=pa is not None and pb is not None and pa!=pb and pa==a[1].get('execution_plan') and pb==b[1].get('execution_plan')
 ca=[x.get('command',{}).get('exit_code') for x in a]; cb=[x.get('command',{}).get('exit_code') for x in b]
 v='PASS_PASS' if ca[0]==ca[1]==0 and cb[0]==cb[1]==0 else 'PASS_FAIL' if ca[0]==ca[1]==0 and cb[0]!=0 else 'FAIL_PASS' if ca[0]!=0 and cb[0]==cb[1]==0 else 'FAIL_FAIL'
 meaningful=mm or resolution or execution or (ca[0]==0 and cb[0]!=0); cause='DEPENDENCY_MEDIATION' if resolution else 'PLUGIN_EXECUTION_INJECTION' if execution else 'PLUGIN_VERSION_SELECTION' if mm else 'UNKNOWN'
 rows.append({'repo':s['repo'],'commit':s['commit'],'analyzable':'true','model_divergence':str(model).lower(),'resolution_divergence':str(resolution).lower(),'execution_divergence':str(execution).lower(),'validation_status':v,'meaningful_divergence':str(meaningful).lower(),'root_cause':cause,'mvnup_relation':'NOT_APPLICABLE','manually_checked':'false','notes':'MEANINGFUL_MODEL' if mm else 'REPRESENTATION_OR_IDENTICAL'})
out=R/'metrics'/'FINAL_REPOSITORY_RESULTS.csv'
out.parent.mkdir(exist_ok=True)
with out.open('w',newline='',encoding='utf-8') as f:
 w=csv.DictWriter(f,fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
(R/'metrics'/'scale_aggregate.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'total':len(rows),'analyzable':sum(x['analyzable']=='true' for x in rows),'meaningful':sum(x['meaningful_divergence']=='true' for x in rows)}))
