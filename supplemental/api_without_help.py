from experiments import *
def one(repo):
    sid=repo.replace('/','__');src=OUT/'api_without_help/sources'/sid
    if not src.exists():shutil.copytree(ROOT/'final_evidence_v1/snapshots'/sid,src)
    caches={rt:fresh_cache('api-only-'+sid+'-'+rt) for rt in ['m3','m4']}
    for rt,n in [('m3',1),('m4',1),('m4',2),('m3',2)]:
        out=OUT/'api_without_help/runs'/sid/f'{rt}-r{n}'
        maven(rt,Path(RT['jdk']),src,caches[rt],out,['validate'],spy=True,timeout=90)
    for c in caches.values():
        assert c.resolve().is_relative_to((OUT/'caches').resolve());shutil.rmtree(c)
def run():
    cases=json.loads((OUT/'instrument/selected_cases.json').read_text())
    with ThreadPoolExecutor(max_workers=2) as pool:
        for f in as_completed([pool.submit(one,repo) for group,repo in cases]):f.result()
if __name__=='__main__':run()
