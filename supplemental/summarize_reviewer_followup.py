"""Summarize the captured common-seed cohort, API execution, and recipe runs."""
from experiments import *
from collections import Counter
sys.path.insert(0,str(ROOT/'scripts'))
from final_evidence_runner import extract_model,model_deltas,flatten_tree,graph_delta

def write(name,rows):
    if not rows:return
    with (CODE/name).open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

def cohort():
    original=[x for x in read(ROOT/'final_evidence_v1/FINAL_PAPER_RESULTS.csv') if x['pom_complete']=='true']
    rows=[];deltas=[]
    for row in original:
        base=OUT/'cohort_offline_recheck'/row['repo'].replace('/','__')
        result=dict(repo=row['repo'],commit=row['commit'],original_model=row['model_comparable'],original_graph=row['resolution_comparable'],original_validation=row['validation_comparable'])
        for layer in ['model','graph','validation']:
            vals={};codes=[];elapsed=0.;fail=[]
            for rt,n in [('m3',1),('m4',1),('m4',2),('m3',2)]:
                folder=base/f'{rt}-r{n}'/layer
                if not (folder/'command.json').exists():continue
                cmd=json.loads((folder/'command.json').read_text());codes.append(cmd['exit_code']);elapsed+=cmd['elapsed_seconds']
                if layer=='validation':vals[rt,n]='TIMEOUT' if cmd['timeout'] else ('PASS' if cmd['exit_code']==0 else 'FAIL');continue
                file=folder/('effective-pom.xml' if layer=='model' else 'tree.json')
                if cmd['exit_code']!=0 or cmd['timeout'] or not file.exists():fail.append('COMMAND_OR_OUTPUT');continue
                try:
                    vals[rt,n]=extract_model(file) if layer=='model' else sorted(flatten_tree(json.loads(file.read_text(encoding='utf-8'))),key=lambda x:json.dumps(x,sort_keys=True))
                except (ET.ParseError,ValueError):fail.append('PARSE')
            result[layer+'_commands']=len(codes);result[layer+'_exit_codes']=json.dumps(codes);result[layer+'_seconds']=round(elapsed,3)
            if len(vals)!=4:status='UNAVAILABLE';positive=False
            elif vals['m3',1]!=vals['m3',2] or vals['m4',1]!=vals['m4',2]:status='WITHIN_RUNTIME_UNSTABLE';positive=False
            elif layer=='validation':status=vals['m3',1]+'_'+vals['m4',1];positive=status in ['PASS_FAIL','FAIL_PASS']
            else:
                status='COMPARABLE'
                if layer=='model':_,detail=model_deltas(row['repo'],row['commit'],vals['m3',1],vals['m4',1]);detail=[x for x in detail if x['category'] not in ['MODEL_PROPERTY_ONLY','MODEL_REPRESENTATION_ONLY']]
                else:detail=graph_delta(row['repo'],row['commit'],row['resolution_target'],vals['m3',1],vals['m4',1])
                positive=bool(detail)
                for d in detail:deltas.append(dict(layer=layer,repo=row['repo'],delta=json.dumps(d,sort_keys=True)))
            result[layer+'_status']=status;result[layer+'_positive']=positive
        rows.append(result)
    write('COHORT_OFFLINE_RECHECK.csv',rows);write('COHORT_OFFLINE_DELTAS.csv',deltas)
    summary=dict(repositories=len(rows),commands=sum(x[l+'_commands'] for x in rows for l in ['model','graph','validation']),layers={l:dict(statuses=dict(Counter(x[l+'_status'] for x in rows)),positive=sum(x[l+'_positive'] for x in rows),positive_repositories=[x['repo'] for x in rows if x[l+'_positive']]) for l in ['model','graph','validation']},formerly_unrun_validation=dict(repositories=sum(x['original_validation']!='true' for x in rows),statuses=dict(Counter(x['validation_status'] for x in rows if x['original_validation']!='true'))))
    dump(CODE/'COHORT_OFFLINE_SUMMARY.json',summary);return summary

def recipes():
    rows=[]
    for p in sorted((OUT/'openrewrite_full_checkouts').glob('*/result.json')):
        obj=json.loads(p.read_text());before={x['path']:x['sha256'] for x in obj['before']};after={x['path']:x['sha256'] for x in obj['after']};cmd=obj['command']
        log=(p.parent/obj.get('recipe_output','recipe')/'stdout.txt').read_text(encoding='utf-8',errors='replace')
        errors=[x for x in log.splitlines() if '[ERROR]' in x]
        post=[]
        offline_post=[]
        for n in [1,2]:
            record=p.parent/f'post-m4-r{n}/command.json'
            if record.exists():post.append(json.loads(record.read_text())['exit_code'])
            record=p.parent/f'post-offline-m4-r{n}/command.json'
            if record.exists():offline_post.append(json.loads(record.read_text())['exit_code'])
        pre={rt:[] for rt in ['m3','m4']}
        pre_frozen={rt:[] for rt in ['m3','m4']};post_frozen=[]
        round_name='final' if (p.parent/'pre-final-m3-r1/command.json').exists() else 'frozen'
        for rt in pre:
            for n in [1,2]:
                record=p.parent/f'pre-{rt}-r{n}/command.json'
                if record.exists():pre[rt].append(json.loads(record.read_text())['exit_code'])
                record=p.parent/f'pre-{round_name}-{rt}-r{n}/command.json'
                if record.exists():pre_frozen[rt].append(json.loads(record.read_text())['exit_code'])
        for n in [1,2]:
            record=p.parent/f'post-{round_name}-m4-r{n}/command.json'
            if record.exists():post_frozen.append(json.loads(record.read_text())['exit_code'])
        rows.append(dict(repo=obj['repo'],source_kind=obj.get('source_kind','frozen POM source copy'),plugin_version=obj['plugin_version'],recipe_artifact=obj['recipe_artifact'],validation_round=round_name,pre_m3_exit_codes=json.dumps(pre['m3']),pre_m4_exit_codes=json.dumps(pre['m4']),pre_frozen_m3_exit_codes=json.dumps(pre_frozen['m3']),pre_frozen_m4_exit_codes=json.dumps(pre_frozen['m4']),exit_code=cmd['exit_code'],timeout=cmd['timeout'],seconds=cmd['elapsed_seconds'],changed_poms=sum(before.get(k)!=after.get(k) for k in set(before)|set(after)),post_m4_exit_codes=json.dumps(post),post_offline_m4_exit_codes=json.dumps(offline_post),post_frozen_m4_exit_codes=json.dumps(post_frozen),diagnostic=' | '.join(errors[:3])))
    write('OPENREWRITE_COMPARISON.csv',rows);summary=dict(cases=len(rows),successful=sum(x['exit_code']==0 for x in rows),cases_with_edits=sum(x['changed_poms']>0 for x in rows),plugin_version='6.46.1',recipe_artifact='org.openrewrite:rewrite-maven:8.90.4',results=rows)
    dump(CODE/'OPENREWRITE_SUMMARY.json',summary);return summary

def dependency_execution():
    rows=[]
    for p in sorted((OUT/'selected_dependency_execution_v2').glob('*/*/selected_artifacts.json')):
        case=p.parent;repo=case.parent.name.replace('__','/');rt,n=case.name.split('-r')
        artifacts=json.loads(p.read_text());command=json.loads((case/'command.json').read_text())
        lines=(case/'stdout.txt').read_text(encoding='utf-8',errors='replace').splitlines()
        rows.append(dict(repo=repo,runtime=rt,repetition=int(n),exit_code=command['exit_code'],checks=';'.join(x for x in lines if x.startswith('CHECK ')),origin=';'.join(x for x in lines if x.startswith('ORIGIN ')),jar_count=len(artifacts['jars']),unmaterialized_nodes=len(artifacts['unmaterialized_nodes'])))
    write('SELECTED_DEPENDENCY_EXECUTION.csv',rows);summary={}
    for repo in sorted({x['repo'] for x in rows}):
        xs=[x for x in rows if x['repo']==repo]
        summary[repo]=dict(runs=len(xs),successful=sum(x['exit_code']==0 for x in xs),checks_per_run=[len(x['checks'].split(';')) for x in xs],checks_equal=len({x['checks'] for x in xs})==1,origins_differ=len({x['origin'] for x in xs})>1)
    dump(CODE/'SELECTED_DEPENDENCY_EXECUTION_SUMMARY.json',summary);return summary

def main():
    result=dict(cohort=cohort(),openrewrite=recipes(),selected_dependency_execution=dependency_execution())
    dump(CODE/'REVIEWER_FOLLOWUP_SUMMARY.json',result);print(json.dumps(result,indent=2))

if __name__=='__main__':main()
