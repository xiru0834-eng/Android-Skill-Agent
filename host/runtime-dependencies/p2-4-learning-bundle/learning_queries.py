"""Four read-only memory APIs. No device, observe, action or model dependency exists here."""
import base64
import json
from bundle_contract import need,key,environment,BundleError
from p24deps import canonical,digest


class LearningQueries:
    def __init__(self,store):
        need(store.read_only is True,'QUERY_REQUIRES_READONLY_STORE');self.store=store

    def _snapshot(self,env,*,expected_revision=None):
        s=self.store.snapshot(environment(env),expected_revision=expected_revision);pages={}
        for row in s['bundles']:
            b=row['bundle']
            for page in b['pages']:
                pages[page['page_id']]={'page':page,'sources':b['sources'],'claims':[c for c in b['claims'] if page['page_id'] in c['page_ids']],
                    'record_revision':row['record_revision'],'bundle_id':b['bundle_id']}
        return s,pages

    @staticmethod
    def _reply(s,status,**values):
        return {'status':status,'environment':s['environment'],'memory_revision':s['memory_revision'],
                'execution_authority':False,'current_ui_confirmed':False,'device_action_calls':0,
                'implicit_observe_calls':0,'scope':'STORED_EVIDENCE_NOT_CURRENT_PHONE','model_calls':0,**values}

    @staticmethod
    def _cursor(cursor,env,op,filters):
        if cursor is None:return None,0
        need(type(cursor) is str and 0<len(cursor)<=2048,'INVALID_CURSOR')
        try:
            p=json.loads(base64.b64decode(cursor,altchars=b'-_',validate=True))
            need(type(p) is dict and set(p)=={'revision','offset','query','checksum'},'INVALID_CURSOR')
            core={k:p[k] for k in ('revision','offset','query')}
            need(p['checksum']==digest(core) and p['query']==digest({'environment':env,'operation':op,'filters':filters}),'INVALID_CURSOR')
            need(type(p['revision']) is int and p['revision']>=0 and type(p['offset']) is int and p['offset']>=0,'INVALID_CURSOR')
            return p['revision'],p['offset']
        except BundleError:raise
        except (ValueError,TypeError,KeyError,UnicodeError) as e:raise BundleError('INVALID_CURSOR') from e

    @classmethod
    def _paginate(cls,items,s,op,filters,limit,cursor):
        need(type(limit) is int and 1<=limit<=100,'INVALID_LIMIT')
        revision,offset=cls._cursor(cursor,s['environment'],op,filters)
        need(revision is None or revision==s['memory_revision'],'REVISION_CONFLICT')
        need(offset<=len(items),'INVALID_CURSOR');tail=offset+limit;next_cursor=None
        if tail<len(items):
            core={'revision':s['memory_revision'],'offset':tail,'query':digest({'environment':s['environment'],'operation':op,'filters':filters})}
            next_cursor=base64.urlsafe_b64encode(canonical({**core,'checksum':digest(core)}).encode()).decode()
        return {'items':items[offset:tail],'next_cursor':next_cursor,'total_count':len(items),'truncated':tail<len(items)}

    def list_pages(self,env,*,limit=20,cursor=None):
        env=environment(env);expected,_=self._cursor(cursor,env,'list_pages',{})
        s,pages=self._snapshot(env,expected_revision=expected)
        items=[{k:r['page'][k] for k in ('page_id','template_id','label','identity_status','entities','navigation_context','known_scope','limitations','source_ids')}
               |{'record_revision':r['record_revision'],'last_stored_observation':r['page']['observation_refs'][-1] if r['page']['observation_refs'] else None}
               for _,r in sorted(pages.items())]
        return self._reply(s,'FOUND' if items else 'NOT_FOUND',**self._paginate(items,s,'list_pages',{},limit,cursor))

    def inspect_page(self,env,page_id):
        key(page_id);s,pages=self._snapshot(env);r=pages.get(page_id)
        return self._reply(s,'FOUND' if r else 'NOT_FOUND',**(r or {'page':None,'sources':[],'claims':[]}))

    def inspect_region(self,env,page_id,region_id):
        key(page_id);key(region_id);s,pages=self._snapshot(env);r=pages.get(page_id)
        region=next((v for v in r['page']['regions'] if v['region_id']==region_id),None) if r else None
        return self._reply(s,'FOUND' if region else 'NOT_FOUND',region=region,
            items=[v for v in r['page']['elements'] if v['element_id'] in region['element_refs']] if region else [],
            sources=r['sources'] if region else [],region_policy='AUXILIARY_INDEX_WHOLE_PAGE_SEARCH_ALLOWED')

    def search_semantic_targets(self,env,*,page_id=None,role=None,text=None,entity_key=None,preferred_region_id=None,limit=20,cursor=None):
        for ident in (page_id,entity_key,preferred_region_id):
            if ident is not None:key(ident)
        for value in (role,text):need(value is None or type(value) is str and 0<len(value)<=256,'INVALID_QUERY')
        need(role is not None or text is not None or entity_key is not None,'SEMANTIC_QUERY_REQUIRED')
        env=environment(env);filters={'page_id':page_id,'role':role,'text':text,'entity_key':entity_key,'preferred_region_id':preferred_region_id}
        expected,_=self._cursor(cursor,env,'search_semantic_targets',filters);s,pages=self._snapshot(env,expected_revision=expected)
        items=[]
        for pid,r in sorted(pages.items()):
            if page_id is not None and page_id!=pid:continue
            for e in r['page']['elements']:
                if e['visible'] is not True or role is not None and e['role']!=role or entity_key is not None and e['entity_key']!=entity_key:continue
                words=' '.join([e['text'] or '',e['content_description'] or ''])
                if text is not None and text.casefold() not in words.casefold():continue
                items.append({'page_id':pid,'element':e,'observation_refs':r['page']['observation_refs'],
                              'record_revision':r['record_revision'],'evidence_status':'RECORDED_VISIBLE_ONLY'})
        items.sort(key=lambda v:(v['element']['region_id']!=preferred_region_id,v['page_id'],v['element']['element_id']))
        status='NOT_FOUND' if not items else 'CANDIDATES' if len(items)==1 else 'AMBIGUOUS'
        return self._reply(s,status,candidate_count=len(items),region_policy='RANK_WITH_WHOLE_PAGE_FALLBACK',
            **self._paginate(items,s,'search_semantic_targets',filters,limit,cursor))
