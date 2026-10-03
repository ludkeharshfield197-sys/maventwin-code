from harness import *

def evaluate():
    assert (R/'evidence/baseline_recheck_completed.json').exists()
    paired=json.loads((R/'metrics/repo_results.json').read_text());sem=json.loads((R/'metrics/semantic-adjudications.json').read_text());baseline=json.loads((R/'metrics/baseline-adjudications.json').read_text())
    assert len(paired)==len(sem)==len(baseline)==30
    count=sum(x['qualifying_repo'] for x in sem);unknown=sum(x['unknown'] for x in paired)/30
    stronger=[x['id'] for x in sem if x['stronger_repo']]
    misses=[x['id'] for x in baseline if x['id'] in stronger and any(c['detection']=='NOT_DETECTED' and c['gate_eligible'] for c in x['cases'])]
    complete_detection=all(x['baseline_available'] and all(c['detection']=='DETECTED_BY_MVNUP' for c in x['cases'] if c['case_id']!='M0') for x in baseline if any(c['case_id']!='M0' for c in x['cases']))
    all_documented=all(c['documented_generic_rule'] for x in sem for c in x['cases'] if c['gate_eligible'])
    if count<=1 or (all_documented and complete_detection):decision='DROP'
    elif unknown<=.2 and (count>=5 or len(stronger)>=3 and len(misses)>=2):decision='GO'
    elif 2<=count<=4:
        mechanisms={c['likely_cause'] for x in sem for c in x['cases'] if c['gate_eligible']}
        decision='MODIFY' if len(mechanisms)==1 else 'NOT_EVALUABLE'
    else:decision='NOT_EVALUABLE'
    result={'evaluated_utc':utc(),'decision':decision,'qualifying_repos':count,'unknown_rate':unknown,'stronger_repos':stronger,'stronger_mvnup_miss_repos':misses,'strong_go_branch_1':count>=5 and unknown<=.2,'strong_go_branch_2':len(stronger)>=3 and len(misses)>=2 and unknown<=.2,'all_documented_and_accurately_detected':all_documented and complete_detection,'conservative_without_dynamic_extension':sum(any(c['case_id'] in ['R1','M1','V1'] and c['gate_eligible'] for c in x['cases']) for x in sem),'conservative_before_final_timestamp_and_failure_cause_correction':sum(x['qualifying_repo'] and x['id'] not in ['mybatis__spring','oshi__oshi','eclipse-ee4j__jaxb-api'] for x in sem),'phase_c_executed':False,'thresholds_changed':False}
    dump(R/'metrics/gate-decision.json',result);print(json.dumps(result,indent=2));return result
if __name__=='__main__':evaluate()
