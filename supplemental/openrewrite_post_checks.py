"""Repeat Maven 4 validation of successfully migrated project copies offline."""
from experiments import *
import experiments
def main():
    base=OUT/'openrewrite_comparison_v3';experiments.SETTINGS=base/'settings.xml'
    dump(base/'post_validation_repository_manifest.json',manifest(base/'repository'))
    for p in sorted(base.glob('*/result.json')):
        obj=json.loads(p.read_text())
        if obj['command']['exit_code']!=0:continue
        for n in [1,2]:
            maven('m4',Path(RT['jdk']),p.parent/'source',base/'repository',p.parent/f'post-offline-m4-r{n}',['validate'],offline=True,timeout=180)
    print('OFFLINE POST CHECKS COMPLETE',flush=True)
if __name__=='__main__':main()
