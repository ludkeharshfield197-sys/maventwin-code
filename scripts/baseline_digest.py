from harness import *

def digest():
    rows=[]
    for s in json.loads((R/'samples/sample_lock.json').read_text())['samples']:
        base=R/'mvnup'/s['id']/'m4-r2/mvnup'
        if not (base/'baseline-integrity.json').exists():continue
        text='\n'.join((base/n).read_text(encoding='utf-8',errors='replace') for n in ['stdout.txt','stderr.txt']);lines=text.splitlines()
        errors=list(dict.fromkeys(x for x in lines if re.search(r'\[ERROR\]|failed|exception|Could not transfer|handshake|Unable to (?:build|resolve)|Cannot (?:build|resolve)',x,re.I) and 'to prevent MalformedInputException' not in x))
        noteworthy=[{'line':i+1,'text':x} for i,x in enumerate(lines) if re.search(r'Upgraded|incompatible|Would (?:remove|replace)|Removed |Replaced |Added |central-publishing|outputTimestamp|(?:source|output)Encoding|transitive.*manag|jcl-over-slf4j',x,re.I)]
        inventories=[json.loads((base/n).read_text()) for n in ['cache-artifacts.json','standalone-cache-artifacts.json']]
        conflicts=[k for k in set(inventories[0])&set(inventories[1]) if k.endswith(('.pom','.jar')) and inventories[0][k]['sha256']!=inventories[1][k]['sha256']]
        row={'id':s['id'],'integrity':json.loads((base/'baseline-integrity.json').read_text()),'strategies_completed':sum('Strategy completed' in x for x in lines),'overall_results':'=== Overall Results ===' in text,'errors':errors,'noteworthy':noteworthy,'artifact_byte_conflicts':sorted(conflicts),'log_sha256':sha(base/'stdout.txt')}
        rows.append(row)
    dump(R/'metrics/baseline-review-digest.json',rows)
    print(json.dumps(rows,ensure_ascii=True,indent=2))
if __name__=='__main__':digest()
