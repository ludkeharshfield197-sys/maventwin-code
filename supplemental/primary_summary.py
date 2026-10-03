"""Recompute the primary layer counts from captured models, graphs and command outcomes."""
from experiments import *
from collections import Counter
sys.path.insert(0,str(ROOT/'scripts'))
from final_evidence_runner import model_deltas,graph_from_run,graph_delta

def main():
    paper=read(ROOT/'final_evidence_v1/FINAL_PAPER_RESULTS.csv');rows=[];md=[];gd=[]
    for row in paper:
        if row['pom_complete']!='true':continue
        base=ROOT/'final_evidence_v1/measurements'/row['repo'].replace('/','__')
        models={rt:[] for rt in ['m3','m4']};validations={rt:[] for rt in models}
        for rt in models:
            for n in [1,2]:
                arm=base/f'{rt}-r{n}';command=arm/'model/command.json';data=arm/'model.json'
                if command.exists() and data.exists() and (arm/'effective-pom.xml').exists():
                    c=json.loads(command.read_text())
                    if c['exit_code']==0 and not c['timeout']:
                        ET.parse(arm/'effective-pom.xml');models[rt].append(json.loads(data.read_text(encoding='utf-8-sig')))
                v=arm/'validation.json'
                if v.exists():validations[rt].append(json.loads(v.read_text(encoding='utf-8-sig')))
        mc=all(len(v)==2 and v[0]==v[1] for v in models.values());d=[]
        if mc:_,d=model_deltas(row['repo'],row['commit'],models['m3'][0],models['m4'][0]);md+=d
        gs={rt:[graph_from_run(base/f'{rt}-r{n}') for n in [1,2]] for rt in models}
        gc=all(v[0] is not None and v[1] is not None and v[0]==v[1] for v in gs.values());g=[]
        if gc:g=graph_delta(row['repo'],row['commit'],row['resolution_target'],gs['m3'][0],gs['m4'][0]);gd+=g
        vc='UNAVAILABLE'
        if all(len(v)==2 for v in validations.values()) and not any(x.get('status')=='UNSAFE_NOT_RUN' for vs in validations.values() for x in vs):
            codes={rt:[x.get('command',{}).get('exit_code') for x in vs] for rt,vs in validations.items()}
            if all(all(x is not None for x in v) for v in codes.values()):
                a,b=codes['m3'],codes['m4']
                vc='PASS_PASS' if a==[0,0] and b==[0,0] else ('PASS_FAIL' if a==[0,0] and all(x!=0 for x in b) else ('FAIL_PASS' if b==[0,0] and all(x!=0 for x in a) else 'FAIL_FAIL'))
        rows.append(dict(repo=row['repo'],model_comparable=mc,model_positive=any(x['category'] not in ['MODEL_PROPERTY_ONLY','MODEL_REPRESENTATION_ONLY'] for x in d),graph_comparable=gc,graph_positive=bool(g),validation=vc))
    summary=dict(candidates=len(paper),frozen=sum(bool(re.fullmatch('[0-9a-f]{40}',x['commit'])) for x in paper),pom_complete=len(rows),model_comparable=sum(x['model_comparable'] for x in rows),model_positive=sum(x['model_positive'] for x in rows),plugin_version_field_repositories=len({x['repo'] for x in md if x['category']=='PLUGIN_VERSION_SELECTION_CHANGED'}),model_delta_rows=len(md),graph_comparable=sum(x['graph_comparable'] for x in rows),graph_positive=sum(x['graph_positive'] for x in rows),graph_delta_rows=len(gd),validation_distribution=dict(Counter(x['validation'] for x in rows)))
    dump(CODE/'PRIMARY_STUDY_SUMMARY.json',summary)
    with (CODE/'PRIMARY_CAPTURED_RESULTS.csv').open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
