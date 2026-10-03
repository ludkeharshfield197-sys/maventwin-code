import csv,json,sys,os,re,time,hashlib,subprocess,xml.etree.ElementTree as ET
from pathlib import Path
from harness import R,runtime_env,run,sha,utc,dump,NS

ROOT=R/'scale_runs'; CACHE_ROOT=R/'tools'/'cache'
M={'m':'http://maven.apache.org/POM/4.0.0'}
PHASE_ORDER={'validate':1,'initialize':2,'generate-sources':3,'process-sources':4,'generate-resources':5,'process-resources':6,'compile':7,'process-classes':8,'generate-test-sources':9,'process-test-sources':10,'generate-test-resources':11,'process-test-resources':12,'test-compile':13,'process-test-classes':14,'test':15,'prepare-package':16,'package':17,'pre-integration-test':18,'integration-test':19,'post-integration-test':20,'verify':21,'install':22,'deploy':23}

def rows():
    with (R/'samples'/'scale_samples.csv').open(encoding='utf-8') as f:return list(csv.DictReader(f))
def source(row):
    p=Path(row['source_path'])
    return p if p and p.exists() else None
def model_file(out,rt): return out/f'effective-pom-{rt}.xml'
def tree_file(out): return out/'dependency-tree.json'
def canon_elem(e):
    tag=e.tag.split('}',1)[-1]
    if tag in {'description','url','name','inceptionYear','organization','licenses','developers','scm','issueManagement','ciManagement','distributionManagement','repositories','pluginRepositories'}: return None
    children=[]
    for c in list(e):
        v=canon_elem(c)
        if v is not None: children.append(v)
    txt=(e.text or '').strip()
    if re.search(r'([A-Za-z]:\\|/tmp/|target/|maventwin)',txt,re.I): txt='<PATH>'
    return {'tag':tag,'text':txt if not children else '', 'children':sorted(children,key=lambda x:json.dumps(x,sort_keys=True))}
def normalized_model(path):
    try:
        root=ET.parse(path).getroot(); wanted={'dependencies','dependencyManagement','build','profiles','modules','properties'}
        vals=[]
        for c in list(root):
            if c.tag.split('}',1)[-1] in wanted:
                v=canon_elem(c)
                if v is not None: vals.append(v)
        return vals
    except Exception:return None
def flatten_tree(x,depth=0,path=()):
    if not isinstance(x,dict):return []
    key=(x.get('groupId',''),x.get('artifactId',''),x.get('version',''),x.get('scope',''))
    out=[{'groupId':key[0],'artifactId':key[1],'version':key[2],'scope':key[3],'depth':depth,'path':'/'.join(path+(key[0]+':'+key[1],))}]
    for c in x.get('children',[]) or []:out.extend(flatten_tree(c,depth+1,path+(key[0]+':'+key[1],)))
    return out
def plan_from_model(path):
    try:
        root=ET.parse(path).getroot();out=[];order=0
        for p in root.findall('.//m:build/m:plugins/m:plugin',M):
            gid=p.findtext('m:groupId','org.apache.maven.plugins',M); aid=p.findtext('m:artifactId','',M); ver=p.findtext('m:version','',M)
            for ex in p.findall('m:executions/m:execution',M):
                phase=ex.findtext('m:phase','',M); eid=ex.findtext('m:id','default',M)
                for g in ex.findall('m:goals/m:goal',M):
                    order+=1; cfg=ex.find('m:configuration',M)
                    out.append({'phase':phase,'plugin_groupId':gid,'plugin_artifactId':aid,'plugin_version':ver,'execution_id':eid,'goal':g.text or '','execution_order':order,'normalized_configuration':canon_elem(cfg) if cfg is not None else {}})
        return sorted(out,key=lambda x:(PHASE_ORDER.get(x['phase'],99),x['execution_order'],x['plugin_groupId'],x['plugin_artifactId']))
    except Exception:return None
def invoke(row,rt,rep):
    src=source(row); sid=row['id']; out=ROOT/sid/f'{rt}-r{rep}'; out.mkdir(parents=True,exist_ok=True)
    if src is None:
        dump(out/'status.json',{'status':'UNKNOWN','reason':'SOURCE_UNAVAILABLE'});return {'status':'UNKNOWN'}
    paths,env=runtime_env('m3' if rt=='m3' else 'm4')
    cache=CACHE_ROOT/('scale-m3' if rt=='m3' else 'scale-m4');cache.mkdir(parents=True,exist_ok=True)
    env.update(GIT_CONFIG_COUNT='1',GIT_CONFIG_KEY_0='safe.directory',GIT_CONFIG_VALUE_0=src.as_posix())
    settings=R/'protocol'/'settings.xml'; model=model_file(out,rt); tree=tree_file(out)
    args=['-B','-ntp','-N','-e','-s',str(settings),'-gs',str(settings),f'-Dmaven.repo.local={cache}','-Dstyle.color=never',
          'org.apache.maven.plugins:maven-help-plugin:3.5.1:effective-pom',f'-Doutput={model}',
          'org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree','-DoutputType=json','-Dverbose=false',f'-DoutputFile={tree}','validate']
    exe=Path(paths[rt])/'bin'/'mvn.cmd'; rec=run([str(exe)]+args,src,out,env,timeout=240)
    status={'runtime':rt,'repeat':rep,'command':rec,'model_exists':model.exists(),'tree_exists':tree.exists(),'validate_exit_code':rec['exit_code'],'model_normalized':normalized_model(model) if model.exists() else None,'execution_plan':plan_from_model(model) if model.exists() else None}
    if tree.exists():
        try:status['dependency_graph']=flatten_tree(json.loads(tree.read_text(encoding='utf-8')))
        except Exception:status['dependency_graph']=None
    dump(out/'normalized.json',status);return status
def worker(i,n):
    rs=[x for x in rows() if x['analyzable'].lower()=='true']
    for j,row in enumerate(rs):
        if j%n!=i:continue
        sid=row['id'];
        for rt in ['m3','m4']:
            for rep in [1,2]:
                p=ROOT/sid/f'{rt}-r{rep}'/'normalized.json'
                if p.exists():continue
                print('RUN',i,j,sid,rt,rep,flush=True);invoke(row,rt,rep)
    print('WORKER_DONE',i,flush=True)
if __name__=='__main__': worker(int(sys.argv[1]),int(sys.argv[2]))
