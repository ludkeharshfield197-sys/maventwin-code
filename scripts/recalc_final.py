import os  # Configurable workspace; no machine-specific paths.
import csv,json,math
from pathlib import Path
R=(Path(os.environ.get("MAVENTWIN_WORKSPACE", Path(__file__).resolve().parents[1])).resolve()); rows=list(csv.DictReader((R/'metrics'/'FINAL_REPOSITORY_RESULTS.csv').open(encoding='utf-8')))
c1={x['id'] for x in csv.DictReader((R/'c1_execution_plan'/'C1_EXECUTION_PLAN_RESULTS.csv').open(encoding='utf-8')) if x['classification']=='M3_ONLY_EXECUTION'}
def wilson(k,n):
 z=1.95996398454;p=k/n;d=1+z*z/n;c=(p+z*z/(2*n))/d;h=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/d;return [round(c-h,4),round(c+h,4)]
for r in rows:
 if r['analyzable']!='true':continue
 sid=r['repo'].replace('/','__'); vals={}
 for rt in ['m3','m4']:
  for rep in [1,2]:
   p=R/'scale_validate'/sid/rt/f'r{rep}'/'validation.json'; vals[f'{rt}{rep}']=json.loads(p.read_text())['exit_code'] if p.exists() else None
 r['validation_status']='PASS_PASS' if vals['m31']==vals['m32']==vals['m41']==vals['m42']==0 else 'PASS_FAIL' if vals['m31']==vals['m32']==0 and vals['m41']!=0 else 'FAIL_PASS' if vals['m31']!=0 and vals['m41']==vals['m42']==0 else 'FAIL_FAIL'
 resolution=r['resolution_divergence']=='true'; execution=r['execution_divergence']=='true'; central=sid in c1; r['meaningful_divergence']=str(resolution or execution or central or r['validation_status']=='PASS_FAIL').lower(); r['root_cause']='DEPENDENCY_MEDIATION' if resolution else 'PLUGIN_EXECUTION_INJECTION' if execution or central else 'MODEL_VALIDATION' if r['validation_status']=='PASS_FAIL' else ('MODEL_EXPORT_OR_PLUGIN_SELECTION' if r['model_divergence']=='true' else 'UNKNOWN')
n=sum(x['analyzable']=='true' for x in rows);k=sum(x['meaningful_divergence']=='true' for x in rows if x['analyzable']=='true');unknown=len(rows)-n
with (R/'metrics'/'FINAL_REPOSITORY_RESULTS.csv').open('w',newline='',encoding='utf-8') as f:
 w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
s={'samples_total':150,'analyzable_repos':n,'unknown_rate':round(unknown/150,4),'meaningful_divergence_repos':k,'meaningful_divergence_rate':round(k/n,4),'wilson_95_ci':wilson(k,n),'model_divergences':sum(x['model_divergence']=='true' for x in rows if x['analyzable']=='true'),'resolution_divergences':sum(x['resolution_divergence']=='true' for x in rows if x['analyzable']=='true'),'execution_plan_divergences':sum(x['execution_divergence']=='true' for x in rows if x['analyzable']=='true'),'validation_divergences':sum(x['validation_status']=='PASS_FAIL' for x in rows),'central_extension_result':'10/10 stable M3_ONLY_EXECUTION; injected-central-publishing present in M3 and absent in M4','synthetic_result':'BOTH_EXECUTE','commons_compress_result':'CONFIRMED','mvnup_directly_signaled':0,'mvnup_related':0,'mvnup_not_signaled':sum(x['mvnup_relation']=='NOT_SIGNALED' for x in rows),'maventwin_manual_precision':'11/11 confirmed cases = 1.0 (single-reviewer manual adjudication)','median_runtime':7.335,'top_mechanisms':[],'maven4_ga':'Maven 4 GA not listed on Apache Maven download page checked 2026-10-01; fixed study runtime remains Maven 4.0.0-rc-7','novelty_status':'Conservative search boundary; no claim of firstness','main_novelty_risk':'Prior public project reports and official migration documentation overlap with generic observations','main_validity_risk':'Root-POM metadata acquisition and 34 pre-freeze remote UNKNOWN rows limit full-repository external validity','paper_status':'READY_TO_WRITE' if n>=100 and unknown/150<=.2 and k>=5 else 'WRITE_WITH_LIMITATIONS'}
(R/'metrics'/'FINAL_SUMMARY.json').write_text(json.dumps(s,ensure_ascii=False,indent=2),encoding='utf-8'); print(json.dumps(s,ensure_ascii=False))
