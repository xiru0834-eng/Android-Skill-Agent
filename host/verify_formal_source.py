"""Pure read-only current formal/source-import gate. No JSON publication authority."""
import json,sys
from pathlib import Path
ROOT=Path(__file__).parent
sys.path.insert(0,str(ROOT/'store'));sys.path.insert(0,str(ROOT/'transport'))
from device_knowledge import KnowledgeLibrary
from device_deps import digest
from device_catalog import Catalog

def verify(host,knowledge):
    if knowledge.get('schema')!='android_published_flow_v1' or knowledge.get('execution_authority') is not False:raise ValueError('KNOWLEDGE_SHAPE')
    if host=='R5CW134LLBZ':
        lib=KnowledgeLibrary.open(ROOT/'private/source-library-v2-r2',approved_roots=[ROOT/'evidence'])
        try:
            source=next((r for r in lib.list_knowledge('FORMAL') if r['version_sha256']==knowledge['source_publication']),None)
            if source is None:raise ValueError('FORMAL_FLOW_NOT_AVAILABLE')
            flow,package=source['flow'],source['package']
        finally:lib.close()
    elif host=='emulator-5556':
        catalog=Catalog(ROOT/'private/target-library-p52-v2')
        imported=catalog.load('source-phone','real.bedroom-light-brightness','1.0.0')
        docs=imported.documents();flow,package=docs['flow.json'],docs['environment.json']
        if docs['scope.json']['source_version_sha256']!=knowledge['source_publication']:raise ValueError('SOURCE_PUBLICATION_MISMATCH')
    else:raise ValueError('UNKNOWN_HOST')
    if knowledge['flow']!=flow or knowledge['package']!=package or digest(flow)!=knowledge['flow_hash']:raise ValueError('FORMAL_SOURCE_CHANGED')
    entry=knowledge['catalog'][0]
    if len(knowledge['catalog'])!=1 or entry['flow_hash']!=digest(flow) or entry['inputs']!=flow['inputs'] or entry['id']!=flow['id'] or entry['version']!=flow['version']:raise ValueError('CATALOG_CHANGED')
    return {'status':'CURRENT_FORMAL_SOURCE_CHECKED','source':'LOCAL_PUBLISHED_LIBRARY' if host=='R5CW134LLBZ' else 'P52_TRUSTED_INERT_IMPORT',
        'execution_authority':False,'flow_hash':digest(flow)}

if __name__=='__main__':
    data=sys.stdin.buffer.read(131073)
    if len(data)>131072:raise ValueError('SIZE_LIMIT')
    print(json.dumps(verify(sys.argv[1],json.loads(data))))
