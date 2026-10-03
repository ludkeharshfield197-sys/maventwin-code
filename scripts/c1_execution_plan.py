import csv,json
from run_scale_experiment import R,plan_from_model

cases=json.loads((R/'metrics'/'extension-binding-cases.json').read_text())
out=R/'c1_execution_plan';out.mkdir(exist_ok=True)
rows=[]
for c in cases:
    sid=c['id']; plans={}; ok=True
    for rt in ['m3','m4']:
        for rep in [1,2]:
            src=R/'metadata_diff'/sid/f'{rt}-r{rep}'/'model'/f'effective-pom-{rt}.xml'
            p=plan_from_model(src) if src.exists() else None; plans[f'{rt}-r{rep}']=p; ok &= p is not None
    if not ok: cls='UNKNOWN'
    else:
        m3=plans['m3-r1']; m4=plans['m4-r1']
        a={(x['phase'],x['plugin_groupId'],x['plugin_artifactId'],x['plugin_version'],x['execution_id'],x['goal'],json.dumps(x['normalized_configuration'],sort_keys=True)) for x in m3}
        b={(x['phase'],x['plugin_groupId'],x['plugin_artifactId'],x['plugin_version'],x['execution_id'],x['goal'],json.dumps(x['normalized_configuration'],sort_keys=True)) for x in m4}
        same_m3=plans['m3-r1']==plans['m3-r2']; same_m4=plans['m4-r1']==plans['m4-r2']
        if not same_m3 or not same_m4: cls='UNKNOWN'
        elif a==b: cls='IDENTICAL'
        k=lambda x:(x['phase'],x['plugin_groupId'],x['plugin_artifactId'],x['plugin_version'],x['execution_id'],x['goal'])
        if a==b: cls='IDENTICAL'
        elif any(k(x) not in {k(y) for y in m4} for x in m3): cls='M3_ONLY_EXECUTION'
        elif any(k(x) not in {k(y) for y in m3} for x in m4): cls='M4_ONLY_EXECUTION'
        elif any(x['plugin_version']!=y['plugin_version'] for x in m3 for y in m4 if (x['phase'],x['plugin_groupId'],x['plugin_artifactId'],x['execution_id'],x['goal'])==(y['phase'],y['plugin_groupId'],y['plugin_artifactId'],y['execution_id'],y['goal'])): cls='VERSION_CHANGED'
        elif any(x['normalized_configuration']!=y['normalized_configuration'] for x in m3 for y in m4 if k(x)==k(y)): cls='CONFIGURATION_CHANGED'
        elif [k(x) for x in m3] != [k(x) for x in m4]: cls='ORDER_CHANGED'
        else: cls='UNKNOWN'
    injected_m3=any(x['execution_id']=='injected-central-publishing' for x in (plans.get('m3-r1') or [])); injected_m4=any(x['execution_id']=='injected-central-publishing' for x in (plans.get('m4-r1') or []))
    row={'id':sid,'classification':cls,'m3_repeatable':plans.get('m3-r1')==plans.get('m3-r2'),'m4_repeatable':plans.get('m4-r1')==plans.get('m4-r2'),'injected_central_m3':injected_m3,'injected_central_m4':injected_m4,'m3_plan_count':len(plans.get('m3-r1') or []),'m4_plan_count':len(plans.get('m4-r1') or [])}
    rows.append(row)
    (out/f'{sid}.json').write_text(json.dumps({'row':row,'plans':plans},ensure_ascii=False,indent=2),encoding='utf-8')
with (out/'C1_EXECUTION_PLAN_RESULTS.csv').open('w',newline='',encoding='utf-8') as f:
    w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
(out/'C1_EXECUTION_PLAN_RESULTS.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'cases':len(rows),'m3_only':sum(x['classification']=='M3_ONLY_EXECUTION' for x in rows),'injected_m3':sum(x['injected_central_m3'] for x in rows),'injected_m4':sum(x['injected_central_m4'] for x in rows)}))
