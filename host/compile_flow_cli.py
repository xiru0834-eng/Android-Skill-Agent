"""Fixed, pure P1 compiler process. No network, Android, oracle or execution rights."""
import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent/'store'))
from device_deps import compiler
data=sys.stdin.buffer.read(131073)
if len(data)>131072:raise ValueError('INPUT_SIZE')
value=json.loads(data)
if set(value)!={'flow','package','task'}:raise ValueError('INPUT_FIELDS')
plan=compiler.compile_flow(value['flow'],value['package'],value['task'],None).to_dict()
sys.stdout.buffer.write(json.dumps(plan,ensure_ascii=False,separators=(',',':')).encode())
