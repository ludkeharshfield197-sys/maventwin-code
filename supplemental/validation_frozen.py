from experiments import *
def one(repo):
    src=full_source(repo)
    if src is None:return
    sid=repo.replace('/','__')
    for jdk,tag in [(Path(RT['jdk']),'jdk21'),(jdk17(),'jdk17')]:
        caches={rt:fresh_cache(f'frozen-validation-{tag}-{sid}-{rt}') for rt in ['m3','m4']}
        for rt,n in [('m3',1),('m4',1),('m4',2),('m3',2)]:
            out=OUT/'validation_frozen'/tag/sid/f'{rt}-r{n}'
            maven(rt,jdk,src,caches[rt],out,['validate'],timeout=120)
        for c in caches.values():
            assert c.resolve().is_relative_to((OUT/'caches').resolve());shutil.rmtree(c)
if __name__=='__main__':
    with ThreadPoolExecutor(max_workers=2) as pool:
        for f in as_completed([pool.submit(one,r) for r in ['apache/commons-io','apache/curator','twilio/twilio-java','eclipse-ee4j/glassfish']]):f.result()
