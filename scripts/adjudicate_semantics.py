from harness import *

def finalize():
    catalog=json.loads((R/'metrics/proposed-semantic-catalog.json').read_text());out=[]
    for x in catalog:
        cases=x['proposed_cases']
        for c in cases:
            c['review_status']='REVIEWED'
            c['gate_eligible']=c['case_id'] in ['R1','M1','M3','V1'] and not x['paired_unknown']
            c['documented_generic_rule']=c['case_id'] in ['R1','M1','M2']
            if c['case_id']=='M0':
                c['adjudication']='Retain reproducible model deltas, but exclude residual reporting conversion, repository declaration, inactive-profile path, plugin ordering and unvalidated residual configuration differences from the semantic gate. No claim that every residual is behaviorally equivalent.'
        residual={
          'jline__jline3':'M3 exports nisse.jgit.dynamicVersion as a property; M4 omits it. Effective project coordinates agree, so no additional behavior claim or gate case.',
          'oshi__oshi':'M3 omits nvdApiKey while M4 exports an unresolved env expression; M3 explicitly exports JUnit-platform skip=false while M4 omits that configuration. Effects are untested and excluded from additional case counts.'
        }.get(x['id'])
        ans={'id':x['id'],'reviewed_utc':utc(),'review_status':'REVIEWED','paired_unknown':x['paired_unknown'],'cases':cases,'meaningful_model':any(c['meaningful'] and c['kind']=='MODEL_DIVERGENCE' for c in cases),'conservative_model':any(c['gate_eligible'] and c['kind']=='MODEL_DIVERGENCE' for c in cases),'qualifying_repo':any(c['gate_eligible'] for c in cases),'broader_meaningful_repo':any(c['meaningful'] for c in cases),'stronger_repo':any(c['stronger_semantic'] and not x['paired_unknown'] for c in cases),'residual_note':residual,'baseline_independent':True}
        dump(R/'metadata_diff'/x['id']/'semantic-adjudication.json',ans);out.append(ans)
    dump(R/'metrics/semantic-adjudications.json',out)
    print(json.dumps({'qualifying':sum(x['qualifying_repo'] for x in out),'meaningful_model':sum(x['meaningful_model'] for x in out),'conservative_model':sum(x['conservative_model'] for x in out),'broader':sum(x['broader_meaningful_repo'] for x in out),'stronger':sum(x['stronger_repo'] for x in out)}))
if __name__=='__main__':finalize()
