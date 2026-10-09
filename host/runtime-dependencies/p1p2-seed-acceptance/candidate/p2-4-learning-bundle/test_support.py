"""Explicit offline public evidence; never an Android capture or a hidden truth provider."""
from bundle_contract import make_bundle,make_source,claim

ENV={'app_package':'example.app','app_build':'1','environment_id':'example','ui_revision':'u0','domain':'EXPERIMENT_APP'}


def bundle_fixture(label='Light 101',*,env=None,page_id='page.a',value=20):
    b=make_bundle(env or ENV,mode='OFFLINE_FIXTURE')
    b['sources']=[make_source('source.a','OFFLINE_DTO',{'heading':label,'value':value},
                basis='OBSERVATION_FACT',grade='OFFLINE_EVIDENCE')]
    region='region.'+page_id
    element={'element_id':'element.'+page_id,'entity_key':None,'region_id':region,'role':'slider',
             'class_name':'android.widget.SeekBar','resource_id':'example.app:id/value','text':'Brightness',
             'content_description':None,'bounds':[0,0,100,20],'visible':True,'enabled':True,'clickable':False,
             'checkable':False,'range':{'kind':'int','min':0,'max':100,'value':value},
             'source_ids':['source.a'],'evidence_grade':'OFFLINE_EVIDENCE'}
    b['pages']=[{'page_id':page_id,'template_id':'template.a','label':label,'identity_status':'UNKNOWN',
        'entities':[],'navigation_context':{'tab':None,'popup':None,'visible_slice':'top'},
        'regions':[{'region_id':region,'label':label,'grouping_status':'OFFLINE_DECLARED',
                    'element_refs':[element['element_id']],'source_ids':['source.a']}],
        'elements':[element],'dynamic_state':[{'value':value}],
        'observation_refs':[{'observation_id':'obs.a','source_id':'source.a','capture':None,'status':'OFFLINE_EVIDENCE'}],
        'source_ids':['source.a'],'limitations':['NOT_REAL_ANDROID_EVIDENCE'],'known_scope':'RECORDED_VISIBLE_ONLY'}]
    b['claims']=[claim('A brightness control was recorded','OBSERVATION_FACT',['source.a'],page_ids=[page_id])]
    return b
