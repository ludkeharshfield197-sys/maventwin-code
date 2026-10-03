"""Create local runtime configuration for a MavenTwin workspace."""
import argparse,json,os
from pathlib import Path

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--jdk',required=True,type=Path)
    p.add_argument('--maven3',required=True,type=Path)
    p.add_argument('--maven4',required=True,type=Path)
    a=p.parse_args()
    root=Path(os.environ.get('MAVENTWIN_WORKSPACE',Path(__file__).resolve().parents[1])).resolve()
    for name,value in [('jdk',a.jdk),('m3',a.maven3),('m4',a.maven4)]:
        if not value.is_dir():p.error(f'{name} directory does not exist: {value}')
    for name in ['protocol','tools','evidence','samples','metrics','verification','synthetic/runs']:
        (root/name).mkdir(parents=True,exist_ok=True)
    (root/'protocol/runtime_paths.json').write_text(json.dumps({'jdk':str(a.jdk.resolve()),'m3':str(a.maven3.resolve()),'m4':str(a.maven4.resolve())},indent=2)+'\n',encoding='utf-8')
    source=Path(__file__).resolve().parents[1]/'protocol/settings.xml'
    settings=root/'protocol/settings.xml'
    if not settings.exists():settings.write_bytes(source.read_bytes())
    print('Runtime configuration created.')

if __name__=='__main__':main()
