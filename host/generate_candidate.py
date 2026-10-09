"""One opt-in current GPT request; protected credential read, no key audit or retries."""
import json,sys
from pathlib import Path
ROOT=Path(__file__).parent
sys.path.insert(0,str(ROOT.parent/'p3-1-draft-generator'))
from learning_request import request_from_store
from draft_generator import Budget,DraftGenerator
from model_api import ModelConfig,UploadGrant
from prepare_g1 import save

def generate(material,out):
    out.mkdir(parents=True,exist_ok=False)
    bundle=json.loads((material/'learning-bundle.json').read_text(encoding='utf-8'))
    request=request_from_store(material/'memory.sqlite',bundle['environment'],[bundle['bundle_id']],
        '学习一个仅调整卧室灯亮度的可复用参数化 Flow。根据公开能力合同和当前公开观察，显式 percent 参数；读取→调用已有能力→断言目标。'
        '不得附带开灯、其他修改或猜未知界面。绝对 setter 的已满足跳过由 Runtime 实现，不需要新分支。旧资料投影器报告的版本关系缺口已有 public.current.build 的当前公开元数据佐证；不能据此自报已执行。')
    save(out/'public-request.json',request)
    sys.path.insert(0,'C:/Users/zz/Documents/ChatGPT/毕设/model-gateway')
    from win_credentials import read_key
    config=ModelConfig('gpt-6-sol',read_key(),'2.00','10.00',
        'https://developers.openai.com/api/docs/pricing?tab=suite ; verified 2026-10-08; conservative short-context standard')
    budget=Budget(max_calls=1,max_corrections=0,total_ms=60000,max_output_tokens=8192,max_cost_usd='1.00')
    save(out/'authority-and-budget.json',{'source':'User prior explicit permission to use GPT for this project and real E2E tests',
         'old_192_quota_reused':False,'current_max_calls':1,'max_cost_usd':'1.00','http_retries':0,
         'upload_scope':'SANITIZED_PUBLIC_EXPERIMENT_APP_MATERIAL','execution_authority':False})
    result=DraftGenerator(out/'audits',budget).run(request,config=config,
         grant=UploadGrant(request['input_digest'],request['environment']))
    save(out/'summary.json',result)
    return result
if __name__=='__main__':
    r=generate(Path(sys.argv[1]),Path(sys.argv[2]));print(json.dumps({k:r.get(k) for k in ('status','calls','audit_directory','evidence_channel')}))
