"""Additional MavenTwin experiments with copied inputs, isolated caches, and bounded runs."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import argparse, csv, hashlib, json, os, re, shutil, subprocess, sys, time, urllib.request, zipfile, xml.etree.ElementTree as ET
from datetime import datetime, timezone
ROOT=Path(os.environ.get('MAVENTWIN_WORKSPACE_ROOT',os.environ.get('MAVENTWIN_WORKSPACE',Path(__file__).resolve().parents[1]))).resolve();OUT=Path(os.environ.get('MAVENTWIN_EXPERIMENT_ROOT',ROOT/'supplementary_results')).resolve();CODE=Path(__file__).resolve().parent
RT=json.loads((ROOT/'protocol/runtime_paths.json').read_text());SETTINGS=ROOT/'protocol/settings.xml'
SEED=OUT/'seed';NS={'m':'http://maven.apache.org/POM/4.0.0'}
PY=Path(sys.executable)
def read(p):
    with p.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def dump(p,v):
    p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2),encoding='utf-8')
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        while b:=f.read(1024*1024):h.update(b)
    return h.hexdigest()
def extended(p):
    text=str(Path(p).resolve())
    return text if os.name!='nt' or text.startswith('\\\\?\\') else '\\\\?\\'+text
def copy_tree(src,dst,**kwargs):return shutil.copytree(extended(src),extended(dst),**kwargs)
def manifest(root):
    base=Path(extended(root))
    return [{'path':p.relative_to(base).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(base.rglob('*')) if p.is_file()]
def process(cmd,cwd,out,timeout=120,env=None):
    out.mkdir(parents=True,exist_ok=True);start=time.time()
    rec={'command':cmd,'cwd':str(cwd),'start_utc':datetime.now(timezone.utc).isoformat(),'timeout':False}
    with (out/'stdout.txt').open('wb') as so,(out/'stderr.txt').open('wb') as se:
        p=subprocess.Popen(cmd,cwd=str(cwd),env=env,stdout=so,stderr=se,stdin=subprocess.DEVNULL)
        try:rec['exit_code']=p.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            rec['timeout']=True
            subprocess.run(['taskkill','/PID',str(p.pid),'/T','/F'],capture_output=True)
            rec['exit_code']=p.wait()
    rec['elapsed_seconds']=round(time.time()-start,3);dump(out/'command.json',rec);return rec
def maven(rt,jdk,cwd,cache,out,goals,props=(),offline=True,timeout=120,recursive=False,spy=False,up=False,spy_phase='package',spy_late=False):
    home=Path(RT[rt]);java=Path(jdk)/'bin/java.exe'
    # Direct invocation of the same ClassWorlds launcher used by mvn.cmd; no orphan cmd.exe on timeout.
    jargs=['--enable-native-access=ALL-UNNAMED'] if rt=='m4' else []
    config=cwd/'.mvn/jvm.config'
    if config.exists():
        import shlex
        jargs+=shlex.split(config.read_text(encoding='utf-8'),posix=True)
    jargs+=['-Xmx1536m',f'-Dclassworlds.conf={home}/bin/m2.conf',f'-Dmaven.home={home}',f'-Dmaven.multiModuleProjectDirectory={cwd}',f'-Dlibrary.jline.path={home}/lib/jline-native']
    if rt=='m4':jargs+=['-Dmaven.mainClass=org.apache.maven.cling.'+('MavenUpCling' if up else 'MavenCling')]
    if spy:
        observer=OUT/'instrument'/('maventwin-observer-late.jar' if spy_late else 'maventwin-observer.jar')
        jargs += [f'-Dmaven.ext.class.path={observer}',f'-Dmaventwin.observer.output={out}/observer', '-Dmaventwin.observer.phase='+spy_phase]
    launcher=next((home/'boot').glob('plexus-classworlds-*.jar'))
    cmd=[str(java)]+jargs+['-classpath',str(launcher),'org.codehaus.plexus.classworlds.launcher.Launcher','-B','-ntp','-e','-s',str(SETTINGS),'-gs',str(SETTINGS),f'-Dmaven.repo.local={cache}','-Dstyle.color=never','-Dmaven.wagon.http.retryHandler.count=1','-Dmaven.resolver.transport.http.connectTimeout=15000','-Dmaven.resolver.transport.http.requestTimeout=30000']
    if offline:cmd+=['-o']
    if up:cmd.remove('-ntp')
    if not recursive and not up:cmd+=['-N']
    cmd+=list(props)+list(goals)
    env=os.environ.copy();env.update(JAVA_HOME=str(jdk),MAVEN_SKIP_RC='1',MAVEN_OPTS='',MAVEN_ARGS='',GIT_TERMINAL_PROMPT='0',GCM_INTERACTIVE='never')
    rec=process(cmd,cwd,out,timeout,env);rec.update(runtime=rt,jdk=str(jdk),offline=offline,cache=str(cache),observer=spy)
    if spy:rec.update(observer_jar_sha256=sha(observer),observer_stage='afterSessionEnd' if spy_late else 'afterProjectsRead',planned_phase=spy_phase)
    dump(out/'command.json',rec);print('RUN',out.relative_to(OUT),rec['exit_code'],rec['elapsed_seconds'],flush=True);return rec
def fresh_cache(tag,seed=SEED):
    dst=OUT/'caches'/hashlib.sha256(tag.encode()).hexdigest()[:12]
    if dst.exists():
        resolved=dst.resolve()
        assert resolved.is_relative_to((OUT/'caches').resolve()) and resolved!=(OUT/'caches').resolve()
        shutil.rmtree(resolved)
    copy_tree(seed,dst);return dst
def prepare():
    OUT.mkdir(parents=True,exist_ok=True)
    backup=CODE/'before';backup.mkdir(exist_ok=True)
    for name in ['main.tex','references.bib','FINAL_STATUS_V2.md']:
        p=backup/name
        if not p.exists():shutil.copy2(ROOT/'paper_v2'/name,p)
    sources=[ROOT/'final_evidence_v1/local_repos/m3',ROOT/'final_evidence_v1/local_repos/m4',ROOT/'paper_fix_v1/local_repos/m3',ROOT/'paper_fix_v1/local_repos/m4']
    conflicts=[];repairs=[];SEED.mkdir(exist_ok=True)
    for src in sources:
        copied=0
        for p in src.rglob('*'):
            if not p.is_file() or p.name.endswith(('.lastUpdated','.lock')):continue
            target=SEED/p.relative_to(src);target.parent.mkdir(parents=True,exist_ok=True)
            valid=True
            if p.suffix=='.jar':valid=p.stat().st_size>0 and zipfile.is_zipfile(p)
            if not valid:repairs.append({'source':str(p),'action':'EXCLUDE_INVALID_JAR'});continue
            if target.exists():
                a=sha(target);b=sha(p)
                if a!=b:conflicts.append({'path':p.relative_to(src).as_posix(),'chosen_sha256':a,'alternative_sha256':b,'alternative_source':str(src)})
                continue
            shutil.copy2(p,target);copied+=1
        print('SEED_SOURCE',src,copied,flush=True)
    dump(OUT/'seed_materialization.json',{'sources':list(map(str,sources)),'priority':'first valid file wins; invalid JARs excluded','conflicts':conflicts,'repairs':repairs})
    dump(OUT/'seed_manifest.json',manifest(SEED));print('SEED_READY',flush=True)
def jdk17():
    target=OUT/'tools';target.mkdir(exist_ok=True)
    dirs=list(target.glob('jdk17*'))
    if dirs and (dirs[0]/'bin/java.exe').exists():return dirs[0]
    url='https://corretto.aws/downloads/latest/amazon-corretto-17-x64-windows-jdk.zip'
    archive=target/'corretto17.zip';req=urllib.request.Request(url,headers={'User-Agent':'MavenTwin-revision'})
    with urllib.request.urlopen(req,timeout=30) as r,archive.open('wb') as f:
        final=r.url;shutil.copyfileobj(r,f)
    with zipfile.ZipFile(archive) as z:
        top=z.namelist()[0].split('/')[0]
        assert all(not n.startswith('/') and '..' not in Path(n).parts for n in z.namelist())
        z.extractall(target)
    dump(target/'jdk17_distribution.json',{'source':url,'resolved':final,'sha256':sha(archive),'bytes':archive.stat().st_size})
    return target/top
def graph_case(repo,jdk,tag):
    sid=repo.replace('/','__');src=ROOT/'final_evidence_v1/snapshots'/sid
    base=OUT/'graph'/tag/sid;cases=[]
    # Every arm starts from a byte-identical copied seed. ABBA arm order with two repetitions each.
    variants=[('baseline',[]),('transitivity_false',['-Dmaven.resolver.dependencyManagerTransitivity=false']),('personality',['-Dmaven.maven3Personality=true']),('both',['-Dmaven.maven3Personality=true','-Dmaven.resolver.dependencyManagerTransitivity=false'])]
    for variant,props in variants:
        existing=base/variant
        expected=[existing/f'{rt}-r{n}/command.json' for rt,n in [('m3',1),('m4',1),('m4',2),('m3',2)]]
        if all(p.exists() for p in expected):
            cases.append({'variant':variant,'records':[json.loads(p.read_text()) for p in expected]});continue
        caches={rt:fresh_cache(f'graph-{tag}-{sid}-{variant}-{rt}') for rt in ['m3','m4']}
        records=[]
        for rt,n in [('m3',1),('m4',1),('m4',2),('m3',2)]:
            out=base/variant/f'{rt}-r{n}';out.mkdir(parents=True,exist_ok=True);tree=out/'tree.json'
            armprops=props if rt=='m4' else []
            rec=maven(rt,jdk,src,caches[rt],out,['org.apache.maven.plugins:maven-dependency-plugin:3.8.1:tree','-DoutputType=json',f'-DoutputFile={tree}'],armprops)
            rec.update(repetition=n,variant=variant,tree_exists=tree.exists());dump(out/'command.json',rec);records.append(rec)
        cases.append({'variant':variant,'records':records})
        # Preserve the frozen seed and raw records, remove only disposable new experiment caches.
        for c in caches.values():
            assert c.resolve().is_relative_to((OUT/'caches').resolve());shutil.rmtree(c)
    dump(base/'result.json',{'repo':repo,'jdk':str(jdk),'variants':cases})
def graph():
    for jdk,tag in [(Path(RT['jdk']),'jdk21'),(jdk17(),'jdk17')]:
        for repo in ['apache/commons-compress','spring-projects/spring-data-neo4j']:graph_case(repo,jdk,tag)
def full_source(repo):
    row=next(x for x in read(ROOT/'samples/scale_samples.csv') if x['repo']==repo)
    sid=row['id'];dst=OUT/'sources'/sid
    if (dst/'.git').exists() and (dst/'pom.xml').exists():return dst
    dst.parent.mkdir(parents=True,exist_ok=True)
    sources=[Path(row['source_path']),ROOT/'final_evidence_v1/git_sources'/sid,ROOT/'paper_fix_v1/git_sources'/sid,ROOT/'paper_fix_v1/full_sources'/sid]
    src=None
    for s in sources:
        if not (s/'.git').exists():continue
        check=subprocess.run(['git','-c','safe.directory=*','-C',str(s),'cat-file','-e',row['commit']],capture_output=True,timeout=20)
        if check.returncode==0:src=s;break
    origin=str(src) if src else f'https://github.com/{repo}.git'
    gitconfig=OUT/'git-task.config';gitconfig.write_text('[safe]\n\tdirectory = *\n[core]\n\tlongpaths = true\n',encoding='utf-8')
    env=os.environ.copy();env.update(GIT_CONFIG_GLOBAL=str(gitconfig),GIT_CONFIG_COUNT='1',GIT_CONFIG_KEY_0='safe.directory',GIT_CONFIG_VALUE_0='*',GIT_TERMINAL_PROMPT='0',GCM_INTERACTIVE='never')
    clone=['git','-c','safe.directory=*','-c','core.longpaths=true','clone','--no-checkout']
    clone+=['--shared'] if src else ['--filter=blob:none','--depth=1']
    rec=process(clone+[origin,str(dst)],ROOT,OUT/'source_acquisition'/sid/'clone',90,env)
    if rec['exit_code']!=0:return None
    process(['git','-C',str(dst),'fetch','--depth=1','origin',row['commit']],ROOT,OUT/'source_acquisition'/sid/'fetch',90,env)
    rec=process(['git','-c','safe.directory=*','-c','core.longpaths=true','-C',str(dst),'checkout','--detach',row['commit']],ROOT,OUT/'source_acquisition'/sid/'checkout',120,env)
    return dst if rec['exit_code']==0 and (dst/'pom.xml').exists() else None
def validation_one(repo):
        src=full_source(repo)
        if src is None:print('SOURCE_UNAVAILABLE',repo,flush=True);return
        sid=repo.replace('/','__')
        for jdk,tag in [(Path(RT['jdk']),'jdk21'),(jdk17(),'jdk17')]:
            for rt,n in [('m3',1),('m4',1),('m4',2),('m3',2)]:
                result=OUT/'validation'/tag/sid/f'{rt}-r{n}'
                if (result/'command.json').exists():continue
                # Genuinely empty local repository per run, independent of old corrupted caches.
                cache=OUT/'caches'/f'validation-clean-{sid}-{tag}-{rt}-r{n}'
                if cache.exists():
                    assert cache.resolve().is_relative_to((OUT/'caches').resolve());shutil.rmtree(cache)
                cache.mkdir(parents=True,exist_ok=True)
                maven(rt,jdk,src,cache,result,['validate'],offline=False,timeout=240)
def validation():
    repos=['apache/commons-io','apache/curator','twilio/twilio-java','eclipse-ee4j/glassfish']
    with ThreadPoolExecutor(max_workers=4) as pool:
        for f in as_completed([pool.submit(validation_one,repo) for repo in repos]):f.result()
def acquire_missing():
    frozen=read(ROOT/'final_evidence_v1/samples/FROZEN_POPULATION.csv');samples={x['repo']:x for x in read(ROOT/'samples/scale_samples.csv')}
    todo=[x for x in frozen if x['recovery_status']=='NETWORK_UNKNOWN']
    def one(row):
        sid=row['repo'].replace('/','__');base=OUT/'acquisition_retry'/sid;base.mkdir(parents=True,exist_ok=True)
        rec={'repo':row['repo'],'commit':row['commit'],'status':'UNKNOWN','root_module_count':'','root_dependency_count':'','root_plugin_count':'','bytes':0}
        url=f'https://raw.githubusercontent.com/{row["repo"]}/{row["commit"]}/pom.xml';start=time.time()
        try:
            with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'MavenTwin-revision'}),timeout=12) as r:b=r.read()
            (base/'pom.xml').write_bytes(b);root=ET.fromstring(b)
            rec.update(status='ROOT_POM_RECOVERED',bytes=len(b),root_module_count=len(root.findall('m:modules/m:module',NS)),root_dependency_count=len(root.findall('m:dependencies/m:dependency',NS)),root_plugin_count=len(root.findall('m:build/m:plugins/m:plugin',NS)),root_pom_sha256=hashlib.sha256(b).hexdigest())
        except Exception as e:rec.update(status='ROOT_ACQUISITION_FAILED',error_type=type(e).__name__,error=str(e))
        rec['elapsed_seconds']=round(time.time()-start,3);dump(base/'result.json',rec);print('ACQUIRE',row['repo'],rec['status'],flush=True);return rec
    with ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(one,todo))
    dump(OUT/'acquisition_retry/results.json',results)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['prepare','graph','validation','acquire','jdk17']);a=p.parse_args()
    globals()[{'acquire':'acquire_missing'}.get(a.mode,a.mode)]()
