"""Deterministic BFS of actual recorded edges. Does not observe, click, invent inverse paths or learn.
This is a read-only route lookup; old records are never a current input permission.
"""
from collections import deque
from bundle_contract import validate_bundle,key,need

def search_known_route(bundle,source_page,target_page):
    return _search_graph(validate_bundle(bundle),source_page,target_page)

def _search_graph(b,source_page,target_page):
    # Pure graph algorithm is separately testable. The public interface never bypasses validation.
    key(source_page);key(target_page)
    pages={p['page_id']:p for p in b['pages']}
    result={'status':'NO_KNOWN_PATH','edges':[],'execution_authority':False,'model_calls':0,
            'scope':'RECORDED_REAL_SCOPED_EDGES_ONLY','current_ui_confirmed':False,
            'claim':'NO_KNOWN_PATH_DOES_NOT_MEAN_APP_FUNCTION_ABSENT'}
    if source_page not in pages:return {**result,'status':'UNKNOWN_SOURCE_PAGE'}
    if source_page==target_page:return {**result,'status':'ALREADY_AT_TARGET'}
    queue=deque([(source_page,[])]);seen={source_page}
    edges=sorted(b['navigation'],key=lambda n:(n['from_page'],n['to_page'] or '',n['interaction_id'] or ''))
    while queue:
        page,path=queue.popleft()
        for edge in edges:
            if edge['status']!='VERIFIED_REAL_SCOPED' or edge['from_page']!=page or edge['to_page'] not in pages:continue
            following=edge['to_page'];route=path+[edge]
            if following==target_page:return {**result,'status':'FOUND','edges':route}
            if following not in seen:seen.add(following);queue.append((following,route))
    return result
