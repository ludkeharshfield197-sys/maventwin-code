from experiments import *

def align(dst,frozen):
    aligned=[]
    for p in frozen.rglob('pom.xml'):
        target=dst/p.relative_to(frozen)
        a=target.read_bytes();b=p.read_bytes()
        assert a.replace(b'\r\n',b'\n')==b.replace(b'\r\n',b'\n')
        if a!=b:target.write_bytes(b);aligned.append(p.relative_to(frozen).as_posix())
    assert sha(dst/'pom.xml')==sha(frozen/'pom.xml')
    return aligned

def run(repo):
    sid=repo.replace('/','__');row=next(r for r in read(ROOT/'samples/scale_samples.csv') if r['repo']==repo)
    dst=OUT/'sources'/sid;preserved=OUT/'source_acquisition'/sid/('preserved-partial-'+str(int(time.time())))
    if dst.exists():
        assert dst.resolve().is_relative_to((OUT/'sources').resolve()) and preserved.resolve().is_relative_to((OUT/'source_acquisition').resolve())
        preserved.parent.mkdir(parents=True,exist_ok=True);dst.rename(preserved)
    dst.mkdir(parents=True);base=OUT/'source_acquisition'/sid/'remote-recovery'
    env=os.environ.copy();env.update(GIT_TERMINAL_PROMPT='0',GCM_INTERACTIVE='never',GIT_CONFIG_GLOBAL=str(OUT/'git-task.config'))
    commands=[['git','init',str(dst)],['git','-C',str(dst),'config','core.autocrlf','false'],['git','-C',str(dst),'remote','add','origin',f'https://github.com/{repo}.git'],['git','-C',str(dst),'fetch','--depth=1','origin',row['commit']],['git','-c','core.longpaths=true','-C',str(dst),'checkout','--detach',row['commit']]]
    for i,cmd in enumerate(commands):
        r=process(cmd,OUT,base/str(i),180,env)
        if r['exit_code']!=0:raise RuntimeError(f'Remote source recovery failed at step {i}')
    frozen=ROOT/'final_evidence_v1/snapshots'/sid
    aligned=align(dst,frozen)
    dump(base/'verified.json',{'repo':repo,'commit':row['commit'],'root_pom_matches_frozen_snapshot':True,'root_pom_sha256':sha(dst/'pom.xml'),'line_ending_alignment_only':aligned})
if __name__=='__main__':run('apache/avro')
