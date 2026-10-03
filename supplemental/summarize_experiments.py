from experiments import *
from collections import Counter
def csvwrite(name,rows):
    if not rows:return
    with (CODE/name).open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def tree_nodes(node,parents=()):
    key=tuple(str(node.get(k,'') or '') for k in ['groupId','artifactId','version','type','classifier','scope','optional'])
    here=[key+(len(parents),parents)]
    coord=':'.join(key[:5])
    for c in node.get('children',[]) or []:here+=tree_nodes(c,parents+(coord,))
    return sorted(here,key=repr)
def graphs():
    rows=[]
    for base in sorted((OUT/'graph').glob('*/*/*')):
        if not base.is_dir():continue
        arms={};records=[]
        for rt in ['m3','m4']:
            vals=[]
            for n in [1,2]:
                p=base/f'{rt}-r{n}/command.json';t=base/f'{rt}-r{n}/tree.json'
                if not p.exists():continue
                r=json.loads(p.read_text());records.append(r)
                if r['exit_code']==0 and not r['timeout'] and t.exists():vals.append(tree_nodes(json.loads(t.read_text(encoding='utf-8-sig'))))
            arms[rt]=vals
        stable=all(len(arms[rt])==2 and arms[rt][0]==arms[rt][1] for rt in ['m3','m4'])
        selected={rt:sorted(set(':'.join(x[:3]) for x in arms[rt][0] if x[1] in ['jcl-over-slf4j','netty-handler','netty-tcnative-classes'])) if arms[rt] else [] for rt in ['m3','m4']}
        rows.append(dict(jdk=base.parent.parent.name,repo=base.parent.name,variant=base.name,runs=len(records),successful_runs=sum(r['exit_code']==0 and not r['timeout'] for r in records),within_runtime_stable=stable,cross_runtime_different=(arms['m3'][0]!=arms['m4'][0] if stable else ''),m3_selected=';'.join(selected['m3']),m4_selected=';'.join(selected['m4'])))
    csvwrite('GRAPH_PROBES.csv',rows);return rows
def validations():
    rows=[]
    for phase in ['validation','validation_frozen']:
        for case in sorted((OUT/phase).glob('*/*')):
            codes={};diagnostics={}
            for rt in ['m3','m4']:
                codes[rt]=[];diagnostics[rt]=[]
                for n in [1,2]:
                    base=case/f'{rt}-r{n}';p=base/'command.json'
                    if not p.exists():continue
                    r=json.loads(p.read_text());codes[rt].append('TIMEOUT' if r['timeout'] else ('PASS' if r['exit_code']==0 else 'FAIL'))
                    log='\n'.join(x.read_text(encoding='utf-8',errors='replace') for x in [base/'stdout.txt',base/'stderr.txt'] if x.exists())
                    errors=[line for line in log.splitlines() if '[ERROR]' in line]
                    diagnostics[rt].append(' | '.join(errors[:5]))
            stable=all(len(codes[rt])==2 and len(set(codes[rt]))==1 for rt in ['m3','m4'])
            rows.append(dict(experiment=phase,jdk=case.parent.name,repo=case.name,m3=';'.join(codes['m3']),m4=';'.join(codes['m4']),status_stable=stable,m3_diagnostics=' || '.join(diagnostics['m3']),m4_diagnostics=' || '.join(diagnostics['m4'])))
    csvwrite('VALIDATION_SUPPLEMENT.csv',rows);return rows
def local(tag):return tag.split('}')[-1]
def canon(e):
    if e is None:return None
    return (local(e.tag),(e.text or '').strip(),tuple(sorted((local(k),v) for k,v in e.attrib.items())),tuple(canon(c) for c in e))
def selected_model(p):
    root=ET.parse(p).getroot();res={}
    for section in ['dependencies','dependencyManagement/dependencies','modules','build/plugins','build/pluginManagement/plugins']:
        el=root.find('/'.join('m:'+x for x in section.split('/')),NS)
        res[section]=canon(el)
    return res
def instruments():
    rows=[]
    for case in sorted((OUT/'instrument/runs').glob('*')):
        outputs={};plans={};equal=[];runs=0;success=0;plan_errors=[]
        for rt in ['m3','m4']:
            outputs[rt]=[];plans[rt]=[]
            for n in [1,2]:
                base=case/f'{rt}-r{n}';cmd=base/'command.json'
                if not cmd.exists():continue
                r=json.loads(cmd.read_text());runs+=1;success+=r['exit_code']==0
                api=base/'observer/000-final-model.xml';help=base/'help-model.xml';plan=base/'observer/000-plan.tsv'
                if not api.exists():api=base/'observer/000-model.xml'
                if api.exists() and help.exists():
                    a=selected_model(api);b=selected_model(help);outputs[rt].append(a);equal.append(a==b)
                    if a!=b:dump(base/'model-crosscheck-differences.json',{'different_sections':[k for k in a if a[k]!=b[k]],'api':a,'help':b})
                if plan.exists():
                    with plan.open(encoding='utf-8-sig') as f:ps=list(csv.DictReader(f,delimiter='\t'))
                    plans[rt].append(ps)
                error=base/'observer/000-plan-error.txt'
                if error.exists():plan_errors.append(error.read_text(encoding='utf-8',errors='replace').splitlines()[0])
        model_stable=all(len(outputs[rt])==2 and outputs[rt][0]==outputs[rt][1] for rt in ['m3','m4'])
        plan_stable=all(len(plans[rt])==2 and plans[rt][0]==plans[rt][1] for rt in ['m3','m4'])
        # Maven 4 renamed lifecycle phases; tuple comparison without phase checks actual ordered plugin invocations.
        def plan_ids(p):return [(x['groupId'],x['artifactId'],x['version'],x['executionId'],x['goal']) for x in p]
        ids_differ=(plan_ids(plans['m3'][0])!=plan_ids(plans['m4'][0])) if plan_stable else ''
        rows.append(dict(repo=case.name,runs=runs,successful_runs=success,extractor_checks=len(equal),api_help_equal=sum(equal),api_repeat_stable=model_stable,api_cross_runtime_different=(outputs['m3'][0]!=outputs['m4'][0] if model_stable else ''),plan_runs=sum(len(v) for v in plans.values()),plan_repeat_stable=plan_stable,ordered_invocations_different=ids_differ,plan_error=' | '.join(sorted(set(plan_errors)))))
    csvwrite('INSTRUMENT_AND_PLAN.csv',rows);return rows
def targets():
    rows=[]
    selection=OUT/'targets/selection.json'
    if not selection.exists():return rows
    data=json.loads(selection.read_text())
    for repo,ts in data['cases']:
        for i,target in enumerate(ts):
            base=OUT/'targets'/repo.replace('/','__')/f'target-{i}';vals={rt:[] for rt in ['m3','m4']};runs=0
            for rt in ['m3','m4']:
                for n in [1,2]:
                    cmd=base/f'{rt}-r{n}/command.json';tree=base/f'{rt}-r{n}/tree.json'
                    if not cmd.exists():continue
                    runs+=1;r=json.loads(cmd.read_text())
                    if r['exit_code']==0 and not r['timeout'] and tree.exists():vals[rt].append(tree_nodes(json.loads(tree.read_text(encoding='utf-8-sig'))))
            stable=all(len(vals[rt])==2 and vals[rt][0]==vals[rt][1] for rt in ['m3','m4'])
            rows.append(dict(repo=repo,target=target,original_target=i==0,runs=runs,comparable=stable,different=(vals['m3'][0]!=vals['m4'][0] if stable else '')))
    csvwrite('TARGET_SENSITIVITY.csv',rows);return rows
def main():
    data={'graph':graphs(),'validation':validations(),'instrument':instruments(),'targets':targets()};dump(CODE/'EXPERIMENT_SUMMARY.json',data)
    print(json.dumps({k:len(v) for k,v in data.items()}))
if __name__=='__main__':main()
