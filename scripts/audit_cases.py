from summarize import read,textlog
from explain_model import *

def audit():
    rows=read(R/'metrics'/'repo_results.json') or [];out=[]
    for row in rows:
        sid=row['id'];base=R/'metadata_diff'/sid
        states=[read(base/f'{rt}-r1'/'normalized-state.json') for rt in ['m3','m4']]
        explanations=[]
        if all('value' in x['model'] for x in states):
            explanations=explain(states[0]['model']['value'],states[1]['model']['value'])
            dump(base/'model-explanation.json',explanations)
        orders={f'{rt}-r{n}':re.findall(r'\[INFO\] --- (.+?) ---',textlog(base/f'{rt}-r{n}'/'validate')) for rt in ['m3','m4'] for n in [1,2]}
        selected_counts={rt:len(states[i]['tree'].get('value',[]))-1 if 'value' in states[i]['tree'] else None for i,rt in enumerate(['m3','m4'])}
        vchanges=[{'section':x['section'],'plugin':x['key'],'m3':x['m3_version'],'m4':x['m4_version']} for x in explanations if 'm3_version' in x and x['m3_version']!=x['m4_version']]
        ans={'id':sid,'confirmation':row['confirmation'],'unknown':row['unknown'],'selected_dependency_nodes':selected_counts,'plugin_version_changes':vchanges,'property_changes':[x for x in explanations if x['section']=='properties'],'changed_model_sections':sorted({x['section'] for x in explanations}),'validation_execution_orders':orders,'same_validation_execution_order':len({jsonkey(x) for x in orders.values()})==1,'graph_deltas':(read(base/'difference-r1.json') or {}).get('tree_differences'),'baseline_recheck_complete':(R/'mvnup'/sid/'m4-r2'/'mvnup'/'baseline-integrity.json').exists()}
        dump(base/'case-audit.json',ans);out.append(ans)
    dump(R/'metrics'/'case-audits.json',out)
    print(json.dumps([{k:x[k] for k in ['id','unknown','selected_dependency_nodes','plugin_version_changes','property_changes','same_validation_execution_order']} for x in out],ensure_ascii=False,indent=2))
if __name__=='__main__':audit()
