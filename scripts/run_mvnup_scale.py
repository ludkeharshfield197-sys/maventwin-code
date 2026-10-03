import csv,sys
from pathlib import Path
from harness import R,runtime_env,run
rows=list(csv.DictReader((R/'samples'/'scale_samples.csv').open(encoding='utf-8')))
def worker(i,n):
 todo=[x for x in rows if x['analyzable'].lower()=='true']
 for j,x in enumerate(todo):
  if j%n!=i:continue
  src=Path(x['source_path']); out=R/'mvnup_scale'/x['id'];
  if (out/'command.json').exists():continue
  if not src.exists(): continue
  paths,env=runtime_env('m4'); cache=R/'tools'/'cache'/'mvnup-scale';cache.mkdir(parents=True,exist_ok=True);out.mkdir(parents=True,exist_ok=True)
  args=['check','-B','--color','never','--directory',str(src),'-s',str(R/'protocol'/'settings.xml'),'-gs',str(R/'protocol'/'settings.xml'),f'-Dmaven.repo.local={cache}']
  run([str(Path(paths['m4'])/'bin'/'mvnup.cmd')]+args,src,out,env,timeout=240)
 print('DONE',i,flush=True)
if __name__=='__main__':worker(int(sys.argv[1]),int(sys.argv[2]))
