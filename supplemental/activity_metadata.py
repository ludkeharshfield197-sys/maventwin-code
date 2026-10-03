from experiments import *
def one(row):
    rec={'repo':row['repo'],'commit':row['commit'],'commit_date_verified':'','method':'UNAVAILABLE'};sid=row['id']
    env=os.environ.copy();env.update(GIT_NO_LAZY_FETCH='1',GIT_TERMINAL_PROMPT='0',GCM_INTERACTIVE='never')
    for src in [Path(row['source_path']),ROOT/'final_evidence_v1/git_sources'/sid]:
        if not (src/'.git').exists():continue
        try:
            p=subprocess.run(['git','-c','safe.directory=*','-C',str(src),'show','--no-patch','--format=%cI',row['commit']],capture_output=True,text=True,timeout=6,env=env)
            if p.returncode==0 and re.match(r'^\d{4}-\d\d-',p.stdout):rec.update(commit_date_verified=p.stdout.strip(),method='FROZEN_COMMIT_OBJECT');return rec
        except Exception:pass
    url=f'https://api.github.com/repos/{row["repo"]}/commits/{row["commit"]}'
    try:
        with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'MavenTwin-revision'}),timeout=12) as r:d=json.loads(r.read())
        assert d['sha']==row['commit'];rec.update(commit_date_verified=d['commit']['committer']['date'],method='GITHUB_COMMIT_API')
        dump(OUT/'activity_metadata'/sid/'commit.json',d)
    except Exception as e:rec['error']=str(e)
    return rec
if __name__=='__main__':
    rs=[x for x in read(ROOT/'samples/scale_samples.csv') if re.fullmatch('[a-f0-9]{40}',x['commit'])]
    with ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(one,rs))
    dump(CODE/'ACTIVITY_METADATA.json',results);print('VERIFIED_COMMIT_DATES',sum(bool(x['commit_date_verified']) for x in results),'/',len(results),flush=True)
