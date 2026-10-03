import csv, json, shutil
from pathlib import Path
from run_scale_experiment import R,ROOT,normalized_model,plan_from_model,flatten_tree

old=json.loads((R/'samples'/'sample_lock.json').read_text())['samples']
for x in old:
    sid=x['id']; src=R/'metadata_diff'/sid
    if not src.exists(): continue
    for rt in ['m3','m4']:
        for rep in [1,2]:
            dest=ROOT/sid/f'{rt}-r{rep}'; dest.mkdir(parents=True,exist_ok=True)
            for kind in ['model','tree','validate']:
                s=src/f'{rt}-r{rep}'/kind; d=dest/kind
                if s.exists() and not d.exists(): shutil.copytree(s,d)
            model=dest/'model'/f'effective-pom-{rt}.xml'; tree=dest/'tree'/'dependency-tree.json'
            commands=[]
            for p in [dest/'model'/'command.json',dest/'tree'/'command.json',dest/'validate'/'command.json']:
                if p.exists(): commands.append(json.loads(p.read_text()))
            code=next((c.get('exit_code') for c in commands if c.get('exit_code')!=0),0)
            st={'runtime':rt,'repeat':rep,'command':{'reused_from':'metadata_diff','commands':commands,'exit_code':code},'model_exists':model.exists(),'tree_exists':tree.exists(),'validate_exit_code':code,'model_normalized':normalized_model(model) if model.exists() else None,'execution_plan':plan_from_model(model) if model.exists() else None}
            if tree.exists():
                try: st['dependency_graph']=flatten_tree(json.loads(tree.read_text(encoding='utf-8')))
                except Exception: st['dependency_graph']=None
            (dest/'normalized.json').write_text(json.dumps(st,ensure_ascii=False,indent=2),encoding='utf-8')
print('POPULATED_EXISTING')
