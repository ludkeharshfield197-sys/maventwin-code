from experiments import *
def run():
    base=OUT/'campaign';base.mkdir(parents=True,exist_ok=True)
    url='https://api.github.com/repos/gnodet/maven4-testing/commits/main'
    req=urllib.request.Request(url,headers={'User-Agent':'MavenTwin-revision','Accept':'application/vnd.github+json'})
    with urllib.request.urlopen(req,timeout=25) as r:meta=json.loads(r.read())
    commit=meta['sha'];url=f'https://codeload.github.com/gnodet/maven4-testing/zip/{commit}'
    with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'MavenTwin-revision'}),timeout=35) as r:b=r.read()
    archive=base/'campaign.zip';archive.write_bytes(b)
    import io
    with zipfile.ZipFile(io.BytesIO(b)) as z:
        assert all('..' not in Path(n).parts and not n.startswith('/') for n in z.namelist());z.extractall(base)
    ids=set();evidence=[]
    for p in base.rglob('maven4-chunks/chunk-*.json'):
        data=json.loads(p.read_text(encoding='utf-8'))
        for item in data.get('include',[]):
            repo=item['repository'];repo=repo if '/' in repo else 'apache/'+repo
            ids.add(repo.lower());evidence.append({'repo':repo,'file':str(p.relative_to(base))})
    for p in base.rglob('*'):
        if not p.is_file() or p.suffix=='.zip':continue
        try:text=p.read_text(encoding='utf-8')
        except Exception:continue
        # Only the campaign's explicit chunk memberships define coverage; incidental URLs are not projects under test.
    inputs=read(ROOT/'samples/scale_samples.csv');pairs=[]
    for r in inputs:pairs.append({'repo':r['repo'],'campaign_listed':r['repo'].lower() in ids})
    dump(CODE/'CAMPAIGN_OVERLAP.json',{'campaign_commit':commit,'source':url,'archive_sha256':sha(archive),'campaign_unique_projects':len(ids),'candidate_overlap':sum(x['campaign_listed'] for x in pairs),'candidate_n':len(pairs),'memberships':pairs,'membership_evidence':evidence,'definition':'Explicit repository memberships in maven4-chunks JSON at the frozen campaign commit; short names are apache repositories per create-chunks.sh.'})
    print('CAMPAIGN',len(ids),sum(x['campaign_listed'] for x in pairs),flush=True)
if __name__=='__main__':run()
