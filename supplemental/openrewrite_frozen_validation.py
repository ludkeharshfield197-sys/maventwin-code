"""Compare migration validation from a common materialized repository."""
from experiments import *
import experiments

def main():
    base=OUT/'openrewrite_full_checkouts';experiments.SETTINGS=base/'settings.xml';cache=base/'repository'
    cases=[]
    for p in sorted(base.glob('*/result.json')):
        obj=json.loads(p.read_text());original=full_source(obj['repo'])
        if original is None:continue
        cases.append((p,obj,original))
        for rt in ['m3','m4']:
            maven(rt,Path(RT['jdk']),original,cache,p.parent/f'materialize-pre-{rt}',['-nsu','validate'],offline=False,timeout=240)
    frozen=base/'frozen_validation_repository'
    if not frozen.exists():copy_tree(cache,frozen)
    dump(base/'frozen_validation_manifest.json',manifest(frozen))
    for p,obj,original in cases:
        for rt,n in [('m3',1),('m4',1),('m4',2),('m3',2)]:
            maven(rt,Path(RT['jdk']),original,frozen,p.parent/f'pre-frozen-{rt}-r{n}',['validate'],offline=True,timeout=180)
        if obj['command']['exit_code']==0:
            for n in [1,2]:maven('m4',Path(RT['jdk']),p.parent/'source',frozen,p.parent/f'post-frozen-m4-r{n}',['validate'],offline=True,timeout=180)
    print('COMMON REPOSITORY MIGRATION VALIDATION COMPLETE',flush=True)

if __name__=='__main__':main()
