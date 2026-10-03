import json,shutil
from pathlib import Path
from harness import R,runtime_env,run,dump
from run_scale_experiment import plan_from_model

src=R/'synthetic'/'project'; outroot=R/'synthetic'/'runs'; outroot.mkdir(parents=True,exist_ok=True)
for rt in ['m3','m4']:
  cache=R/'tools'/'cache'/('scale-m3' if rt=='m3' else 'scale-m4'); cache.mkdir(parents=True,exist_ok=True)
  if rt=='m4':
    s=R/'tools'/'cache'/'m3'/'com'/'maventwin'; d=cache/'com'/'maventwin'
    if s.exists() and not d.exists(): shutil.copytree(s,d)
  paths,env=runtime_env(rt); env.update(GIT_CONFIG_COUNT='1',GIT_CONFIG_KEY_0='safe.directory',GIT_CONFIG_VALUE_0=src.as_posix())
  for rep in [1,2]:
    target=src/'target'; shutil.rmtree(target,ignore_errors=True)
    o=outroot/f'{rt}-r{rep}'; o.mkdir(parents=True,exist_ok=True); model=o/f'effective-pom-{rt}.xml'
    args=['-B','-ntp','-e','-s',str(R/'protocol'/'settings.xml'),'-gs',str(R/'protocol'/'settings.xml'),f'-Dmaven.repo.local={cache}','-Dstyle.color=never','org.apache.maven.plugins:maven-help-plugin:3.5.1:effective-pom',f'-Doutput={model}','validate']
    rec=run([str(Path(paths[rt])/'bin'/'mvn.cmd')]+args,src,o,env,timeout=180)
    marker=target/'maventwin-marker.txt'; plan=plan_from_model(model) if model.exists() else None
    dump(o/'result.json',{'runtime':rt,'repeat':rep,'command':rec,'marker_exists':marker.exists(),'marker_content':marker.read_text() if marker.exists() else None,'execution_plan':plan})
rows=[]
for rt in ['m3','m4']:
  for rep in [1,2]: rows.append(json.loads((outroot/f'{rt}-r{rep}'/'result.json').read_text()))
cat='UNKNOWN'
if all(x['command']['exit_code']==0 for x in rows):
  m3=all(x['marker_exists'] for x in rows if x['runtime']=='m3');m4=all(x['marker_exists'] for x in rows if x['runtime']=='m4')
  cat='BOTH_EXECUTE' if m3 and m4 else 'M3_ONLY_EXECUTES' if m3 else 'M4_ONLY_EXECUTES' if m4 else 'NEITHER_EXECUTES'
dump(R/'synthetic'/'SYNTHETIC_RESULT.json',{'classification':cat,'runs':rows})
print(json.dumps({'classification':cat,'exit_codes':[x['command']['exit_code'] for x in rows],'markers':[x['marker_exists'] for x in rows]}))
