"""Finalize case coverage after reviewing baseline-review-digest and original logs.

Guarded against keyword evidence that would invalidate the reviewed absent-case result.
"""
from harness import *

def finalize():
    assert (R/'evidence/baseline_recheck_completed.json').exists()
    semantics=json.loads((R/'metrics/semantic-adjudications.json').read_text())
    digest={x['id']:x for x in json.loads((R/'metrics/baseline-review-digest.json').read_text())}
    out=[]
    for s in semantics:
        sid=s['id'];d=digest[sid];base=R/'mvnup'/sid/'m4-r2/mvnup';log=(base/'stdout.txt').read_text(encoding='utf-8',errors='replace')+'\n'+(base/'stderr.txt').read_text(encoding='utf-8',errors='replace')
        incidental=[e for e in d['errors'] if sid=='spring-projects__spring-retry' and ('Unable to locate English counter names in registry Perflib 009' in e or 'com.sun.jna.platform.win32.Win32Exception:' in e)]
        model_errors=[e for e in d['errors'] if e not in incidental]
        available=d['integrity']['exit_code']==0 and not d['integrity']['timeout'] and d['overall_results'] and d['strategies_completed']==11 and not model_errors and not d['artifact_byte_conflicts']
        cases=[]
        for c in s['cases']:
            cid=c['case_id'];detection='NOT_DETECTED'
            if cid=='M0':
                detection='NOT_APPLICABLE';reason='Residual exported-model differences excluded from the semantic coverage denominator; unverified behavior implications.'
            elif not available:
                detection='NOT_APPLICABLE';reason='Baseline analysis incomplete: internal errors/timeout or missing strategy completion. No miss inferred from absence.'
            elif cid=='R1':
                assert not re.search(r'jcl-over-slf4j|dependencyManagerTransitivity|transitive.{0,30}management',log,re.I), 'Review newly relevant resolution message'
                reason='All 11 strategies completed without model-analysis errors; no warning identifies the selected jcl-over-slf4j version change or its management path.'
            elif cid=='M3':
                assert not re.search(r'central-publishing|injected-central-publishing',log,re.I), 'Review newly relevant extension message'
                reason='All 11 strategies completed without model-analysis errors; no warning names the Central Publishing injected execution or its absence in the M4 model.'
            elif cid=='M2':
                assert not re.search(r'outputTimestamp|project.build.sourceEncoding|project.reporting.outputEncoding',log,re.I), 'Review newly relevant default-property message'
                reason='No recommendation identifies the observed inherited encoding/outputTimestamp defaults; unrelated plugin upgrades are not this case.'
            elif cid=='M1':
                upgraded=[n for n in d['noteworthy'] if 'Upgraded' in n['text']]
                affected=[p['plugin'] for p in c['details']]
                relevant=[n for n in upgraded if any(p in n['text'] for p in affected)]
                assert not relevant, f'Review possible partial plugin-version detection: {sid} {relevant}'
                reason='No concrete upgrade recommendation names any plugin whose active effective-model version changed in this paired root experiment. Unrelated root/child upgrades are retained but do not detect it.'
            else:raise AssertionError('Unreviewed case '+cid)
            cases.append({'case_id':cid,'kind':c['kind'],'detection':detection,'gate_eligible':c['gate_eligible'],'reason':reason,'evidence':{'stdout':'m4-r2/mvnup/stdout.txt','stdout_sha256':sha(base/'stdout.txt'),'noteworthy_lines':d['noteworthy'],'errors':d['errors']}})
        status='NOT_DETECTED' if any(c['detection']=='NOT_DETECTED' for c in cases) else 'NOT_APPLICABLE'
        ans={'id':sid,'reviewed_utc':utc(),'review_status':'REVIEWED','status':status,'baseline_available':available,'incidental_diagnostics':incidental,'model_analysis_errors':model_errors,'artifact_byte_conflicts':d['artifact_byte_conflicts'],'baseline_scope':'mvnup recursive POM checks; comparison matched only to observed root-POM cases','source_unchanged':d['integrity']['source_unchanged'],'cases':cases,'first_run_preserved':True,'paired_labels_changed':False}
        dump(R/'mvnup'/sid/'adjudication.json',ans);out.append(ans)
    dump(R/'metrics/baseline-adjudications.json',out)
    counts={'available':sum(x['baseline_available'] for x in out),'unavailable':[x['id'] for x in out if not x['baseline_available']],'miss_repos':sum(any(c['detection']=='NOT_DETECTED' for c in x['cases']) for x in out),'conservative_miss_repos':sum(any(c['detection']=='NOT_DETECTED' and c['gate_eligible'] for c in x['cases']) for x in out),'case_detections':{k:sum(c['detection']==k for x in out for c in x['cases']) for k in ['DETECTED_BY_MVNUP','PARTIALLY_DETECTED','NOT_DETECTED','NOT_APPLICABLE']}}
    dump(R/'metrics/baseline-counts.json',counts);print(json.dumps(counts,indent=2))
if __name__=='__main__':finalize()
