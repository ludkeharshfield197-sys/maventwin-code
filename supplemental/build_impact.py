from experiments import *
def one(group,repo):
    sid=repo.replace('/','__');original=full_source(repo)
    if original is None:dump(OUT/'build_impact'/sid/'source-unavailable.json',{'repo':repo});return
    for rt,n in [('m3',1),('m4',1),('m4',2),('m3',2)]:
        out=OUT/'build_impact'/sid/f'{rt}-r{n}'
        if (out/'command.json').exists():continue
        src=OUT/'bs'/hashlib.sha256((sid+rt+str(n)).encode()).hexdigest()[:10]
        if src.exists():
            assert src.resolve().is_relative_to((OUT/'bs').resolve());shutil.rmtree(src)
        src.parent.mkdir(parents=True,exist_ok=True)
        def longpath(p):
            text=str(p.resolve())
            return text if os.name!='nt' or text.startswith('\\\\?\\') else '\\\\?\\'+text
        shutil.copytree(longpath(original),longpath(src),ignore=shutil.ignore_patterns('.git','target'))
        cache=fresh_cache(f'build-{sid}-{rt}-{n}')
        before=sha(src/'pom.xml')
        maven(rt,Path(RT['jdk']),src,cache,out,['package','-DskipTests=true','-Dmaven.javadoc.skip=true'],offline=False,timeout=180)
        dump(out/'source_integrity.json',{'root_pom_before':before,'root_pom_after':sha(src/'pom.xml'),'root_pom_unchanged':before==sha(src/'pom.xml')})
        dump(out/'target_manifest.json',manifest(src/'target') if (src/'target').exists() else [])
        assert cache.resolve().is_relative_to((OUT/'caches').resolve());shutil.rmtree(cache)
def run():
    prov=read(ROOT/'artifacts/reviewer_revision/model/model_delta_summary.csv');groups=[]
    for group in ['source','runtime','unresolved']:
        candidates=[x for x in prov if (x['project_pom_evidence']=='true' if group=='source' else (x['runtime_only_evidence']=='true' if group=='runtime' else x['project_pom_evidence']!='true' and x['runtime_only_evidence']!='true'))]
        groups+= [(group,r['repo']) for r in sorted(candidates,key=lambda r:r['repo'])[:4]]
    # Twelve stratified original model-positive revisions, full checkouts, bounded non-recursive package.
    dump(OUT/'build_impact/selection.json',{'cases':groups,'task':'package -DskipTests=true -Dmaven.javadoc.skip=true, root -N, repeats ABBA','purpose':'Observe actual root plugin invocations and package outcomes; application test behavior remains a separate construct.'})
    with ThreadPoolExecutor(max_workers=3) as pool:
        for f in as_completed([pool.submit(one,*c) for c in groups]):f.result()
if __name__=='__main__':run()
