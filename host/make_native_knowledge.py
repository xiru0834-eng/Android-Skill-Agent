"""Published source -> inert, locally reviewable plan template; no transferred approval."""
import copy,json,sys
from pathlib import Path
ROOT=Path(__file__).parent
sys.path.insert(0,str(ROOT/'store'))
from device_knowledge import KnowledgeLibrary
from device_deps import compiler,digest
from prepare_g1 import save

def build(flow,package,task,publication):
    sample=copy.deepcopy(task);sample['authorization_ref']='local.user.confirmation.required'
    sample['cancellation_token_ref']='cancel.template'
    template=compiler.compile_flow(flow,package,sample,None).to_dict()
    # These are bookkeeping only, never business semantics or input rights.
    metadata={'task_id','task_hash','host_device_id','authorization_ref','cancellation_token_ref'}
    slots=[]
    def changes(left,right,path=()):
        if type(left) is dict:
            if set(left)!=set(right):raise ValueError('COMPILER_SHAPE_CHANGED')
            for k in left:
                if not path and k in metadata:continue
                yield from changes(left[k],right[k],path+(k,))
        elif type(left) is list:
            if len(left)!=len(right):raise ValueError('COMPILER_SHAPE_CHANGED')
            for i,(a,b) in enumerate(zip(left,right)):yield from changes(a,b,path+(i,))
        elif type(left)!=type(right) or left!=right:yield list(path)
    entities={}
    for spec in flow['inputs']:
        name=spec['name']
        if spec['type']=='entity':
            # Current reviewed source scope, not equality of display names.
            entities[name]=[sample['inputs'][name]['entity_id']];continue
        if spec['type']!='integer':raise ValueError('TEMPLATE_TYPE_NOT_YET_SUPPORTED')
        changed=copy.deepcopy(sample)
        n=spec['minimum'] if sample['inputs'][name]!=spec['minimum'] else spec['maximum']
        changed['inputs'][name]=n
        second=compiler.compile_flow(flow,package,changed,None).to_dict()
        for path in changes(template,second):slots.append({'input':name,'path':path})
    entry={'id':flow['id'],'version':flow['version'],'flow_hash':digest(flow),'purpose':flow['purpose'],
        'inputs':flow['inputs'],'entities':entities,'verified_parameters':[p['inputs'] for p in publication['eligible_points']],
        'allowed_effects':flow['allowed_effects'],'must_preserve':flow['must_preserve'],
        'preserve_unmentioned':flow['verification']['preserve_unmentioned'],'whole_parameter_domain_verified':False}
    return {'schema':'android_published_flow_v1','flow':flow,'package':package,'flow_hash':digest(flow),
        'catalog':[entry],'compiled_template':template,'template_inputs':sample['inputs'],'parameter_slots':slots,
        'task_template':sample,'source_publication':publication['version_sha256'],
        'source_origin':'REAL_GPT_DOCUMENTATION_AND_FORMAT_REVIEW_ASSISTED','execution_authority':False}

if __name__=='__main__':
    library=KnowledgeLibrary.open(ROOT/'private/source-library-v2-r2',approved_roots=[ROOT/'evidence'])
    try:
        rows=library.list_knowledge('FORMAL')
        if len(rows)!=1:raise ValueError('FORMAL_SOURCE_REQUIRED')
        row=rows[0]
        task=json.loads((ROOT/'evidence/g2-reviewed-r2/task.json').read_text(encoding='utf-8'))
        save(Path(sys.argv[1]),build(row['flow'],row['package'],task,row))
    finally:library.close()
