"""Trusted P3 candidate transport. No oracle dependency and no P4 publication prerequisite."""
import sys,uuid
from pathlib import Path
ROOT=Path(__file__).parent
sys.path.insert(0,str(ROOT/'store'))
from device_deps import compiler,records,digest
from lab_transport import execute

def validate_candidate(library,key,task,host,authority):
    if type(authority) is not records.ValidationAuthority or not authority.confirmed or authority.version_key!=key:
        raise ValueError('VALIDATION_AUTHORITY_REQUIRED')
    record=library.flows.load(key)
    if record['state'] not in {'CHECKED','VALIDATED_SCOPE'}:raise ValueError('NOT_CHECKED')
    data=compiler.compile_flow(record['flow'],record['package'],task,None).to_dict()
    result=execute(host,data,mode='CANDIDATE_VALIDATION',writes=data['actual_write_set'])
    proof=None
    if result.get('final_status') in {'SUCCESS','NO_ACTION_REQUIRED'} and result.get('verification_result') is True:
        if (result.get('channel')!='ANDROID_NATIVE' or result.get('mode')!='CANDIDATE_VALIDATION' or
            result.get('service_entry_hit') is not True or result.get('flow_hash')!=data['flow_hash'] or
            result.get('package_hash')!=data['source_package_raw_hash'] or
            result.get('completed_steps')!=len(data['steps']) or result.get('final_observation_complete') is not True):
            raise ValueError('NATIVE_EVIDENCE_MISMATCH')
        calls=[s['runtime_receipt']['calls'][0] for s in result['steps'] if s['op']=='CALL' and s['runtime_receipt']['execution_actions']]
        proof=records._issue_evidence({'evidence_id':'execution.'+uuid.uuid4().hex,'channel':'REAL_ANDROID_FLOW_VALIDATION',
            'version_sha256':record['sha256'],'flow_hash':data['flow_hash'],'package_hash':data['package_hash'],
            'plan_hash':digest(data),'registry_hash':data['registry_hash'],'environment_hash':data['environment_hash'],
            'environment':data['environment'],'source_package_raw_hash':data['source_package_raw_hash'],
            'host_device_id':data['host_device_id'],'inputs':task['inputs'],'initial_state':result['initial_state'],
            'final_state':result['final_observed_state'],'ordered_calls':calls,'sequence_verified':True,
            'verifier':'G1_CURRENT_PUBLIC_REOBSERVE_AFTER_EACH_CALL','read_only_target_satisfied':not calls,
            'parameter_domain_verified':False,'device_execution_verified':True,'execution_authority':False,
            'native_request_id':result['request_id'],'native_process_session':result['process_session']})
    return data,result,proof
