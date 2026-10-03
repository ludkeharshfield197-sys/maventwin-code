import csv,sys
from pathlib import Path
from harness import R,runtime_env,run,dump
rows=list(csv.DictReader((R/'samples'/'scale_samples.csv').open(encoding='utf-8')))
def worker(i,n):
 todo=[x for x in rows if x['analyzable'].lower()=='true']
 for j,x in enumerate(todo):
  if j%n!=i:continue
  src=Path(x['source_path'])
  if not src.exists():continue
  for rt in ['m3','m4']:
   paths,env=runtime_env(rt);cache=R/'tools'/'cache'/('scale-m3' if rt=='m3' else 'scale-m4'); out=R/'scale_validate'/x['id']/rt
   for rep in [1,2]:
    d=out/f'r{rep}';
    if (d/'command.json').exists():continue
    args=['-B','-ntp','-N','-e','-s',str(R/'protocol'/'settings.xml'),'-gs',str(R/'protocol'/'settings.xml'),f'-Dmaven.repo.local={cache}','-Dstyle.color=never','validate']
    rec=run([str(Path(paths[rt])/'bin'/'mvn.cmd')]+args,src,d,env,timeout=240)
    dump(d/'validation.json',{'runtime':rt,'repeat':rep,'exit_code':rec['exit_code'],'command':rec})
 print('DONE',i,flush=True)
if __name__=='__main__':worker(int(sys.argv[1]),int(sys.argv[2]))
