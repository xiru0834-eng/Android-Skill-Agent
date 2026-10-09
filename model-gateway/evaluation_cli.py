"""Offline evaluation entry point. No phone access or model requests in this CLI."""
import argparse
import csv
import json
import shutil
from pathlib import Path
from evaluation_framework import VERSION, compare_reports, summarize, validate_plan
from evaluation_import import CAPABILITIES, RUN_FILES, audit_campaign, dump, import_partial, sha

LABELS=dict(teaching='示教',language='语言理解',execution='执行',migration='导入迁移',fault='故障处理',ux='使用入口')
STATUS=dict(NOT_TESTED='未测试',INSUFFICIENT_EVIDENCE='证据不足',OBSERVED_FAILURE='观察到失败',OBSERVED_PASS='本批通过')


def csv_cell(value):
    if isinstance(value,str) and value.lstrip().startswith(('=','+','-','@')):return "'"+value
    return value


def rate(r):
    return f"{r['numerator']}/{r['denominator']}" if r['value'] is not None else '未测'


def write_csv(path,fields,rows):
    with path.open('x',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
        writer.writerows({k:csv_cell(row.get(k)) for k in fields} for row in rows)


def write_report(root,p,observations):
    root=Path(root);report=summarize(p,observations)
    paths=[root/n for n in ('report.json','report.md','cases.csv','capabilities.csv','observations.json')]
    if any(f.exists() for f in paths):raise FileExistsError('Refuse overwriting report')
    dump(root/'observations.json',observations);dump(root/'report.json',report)
    write_csv(root/'cases.csv',['id','stage','environment','family','repeat','state','error','evidence_basis',
                              'failed_checks','reported_reason','failure_step','failure_control','terminal_phase'],
              [dict(r,failed_checks=';'.join(r.get('failed_checks',[])),
                    **{k:r['metrics'].get(k) for k in ('reported_reason','failure_step','failure_control','terminal_phase')})
               for r in report['cases']])
    write_csv(root/'capabilities.csv',['id','label','status','planned','scored','minimum_repeats','inconsistent_families','evidence_level'],
              list(report['capabilities'].values()))
    lines=['# GUI技能评估报告','',f"实验：{p['campaign']}；变体：{p['variant']}；阶段：{p['phase']}；评分：{VERSION}。",'',
           '这是已有原始证据的重算，没有新增手机实验或模型请求。' if p['phase']=='retrospective' else
           '按冻结计划计分；未采集证据的用例保持未运行。','',
           '## 分阶段结果','',
           '| 阶段 | 通过/计划 | 通过/可评分 | 失败 | 阻塞 | 缺证据/无效 | 未运行 |',
           '| --- | ---: | ---: | ---: | ---: | ---: | ---: |']
    for stage,s in report['stages'].items():
        lines.append(f"| {LABELS[stage]} | {rate(s['pass_planned'])} | {rate(s['pass_scored'])} | {s['states']['FAIL']} | {s['states']['BLOCKED']} | {s['states']['INVALID']} | {s['states']['NOT_RUN']} |")
    lines+=['','正确故障停止不计为任务完成；自动化示范不计为真人体验；导入审核不计为跨设备任务完成。','',
            '## 执行与代价','',
            '| 环境 | 可评分 | 真实完成 | 正确报告完成 | 误报 | 非目标改变 | 执行p50/p95（毫秒） |',
            '| --- | ---: | ---: | ---: | ---: | ---: | --- |']
    for env,s in report['stages'].get('execution',{}).get('environments',{}).items():
        t=s['timings']['execution_ms']
        lines.append(f"| {env} | {s['scored']} | {rate(s['actual_completion'])} | {rate(s['confirmed_completion'])} | {rate(s['false_success'])} | {rate(s['non_target_violation'])} | {t['p50']} / {t['p95']} |")
    lines+=['','此表按环境分组，但四步/八步及初态仍可能不同；逐例和能力表保留细分。不用该混合耗时推断版本提速。',
            '执行计时不含GPT、用户确认及测试准备。端到端计时尚未完整采集。失败的已记录耗时保留，未知耗时不补零。','',
            '## 能力覆盖','',
            '| 能力 | 本批状态 | 通过/计划 | 最少同条件重复 | 重复结果不一致的任务族 |',
            '| --- | --- | ---: | ---: | ---: |']
    for c in report['capabilities'].values():
        lines.append(f"| {c['label']} | {STATUS[c['status']]} | {rate(c['pass_planned'])} | {c['minimum_repeats']} | {c['inconsistent_families']} |")
    lines+=['','“未测试”指本评估集合没有证据，不等于项目历史从未做过。不同环境不合并为同条件重复；本批通过不等于普遍可靠。',
            '样本较少或最少重复不足3次时标记SMALL_SAMPLE。比例区间仅作固定样本描述，详见report.json及[NIST方法](https://www.itl.nist.gov/div898/handbook/prc/section2/prc241.htm)。','',
            '## 下一轮需要补什么','',
            '- 真人独立完成新示范，采集求助次数、录制失败原因、审核修改和保存结果。',
            '- 记录从提交请求到最终结果的完整耗时，区分模型、确认等待、执行和冷启动。',
            '- 为参数泛化、新App绑定及更多任务冻结独立测试集，不沿用现有成功率。',
            '- 同初态/目标/设备多次复跑，并保存所有未运行、阻塞与失败。','',
            '## 审计与来源','',
            'plan.json和plan.sha256固定用例；原始证据路径列在每条用例的proof.files中；evidence-sha256.json用于发现文件变化。',
            '每次重审重新执行原始账本/语言/示教检查。SHA-256不是外部签名，不能证明证据的真实采集来源。',
            '入口取消包含独立输入账本和当时测试器的结果未变化断言；不把它升级为真人可用性证明。',
            ('本集合是历史导入，缺少统一随机化/配对条件，当前不可直接拿来宣称公平A/B提升。'
             if p['phase']=='retrospective' else
             '本批按冻结计划采集。没有匹配的配对比较条件时，不据此宣称公平A/B提升。'),'']
    if report['alerts']:lines+=['告警：'+', '.join(report['alerts']),'']
    if p.get('incidents'):
        lines+=['准备阶段事件保留：','']+[f"- {e['path']}：{e['note']}" for e in p['incidents']]+['']
    (root/'report.md').write_text('\n'.join(lines),encoding='utf-8')
    return report


def create_plan(root,definition=None):
    root=Path(root)
    if root.exists():raise FileExistsError('Refuse overwriting plan')
    cases=[]
    for i in range(3):
        expected=dict(skill='lamp',condition='none',repeat=i,initial=[0,40,1,3])
        cases.append(dict(id=f'run-{i:03d}',stage='execution',family='lamp60-from-off40',repeat=i,
                     capabilities=['exec.multipage','exec.partial'],environment='S23+',expected='complete',
                     dimensions=dict(pages=2,steps=4,goal=[1,60,None,None],budget_ms=30000,source='AUTOMATED'),
                     proof=dict(kind='partial',expected=expected,
                                files={k:f'proof/run-{i:03d}/{k}.json' for k in RUN_FILES})))
    p=dict(schema=1,framework=VERSION,campaign=root.name,phase='development',variant='v24-template',
           comparison={},capabilities=[dict(id=k,label=v) for k,v in CAPABILITIES],cases=cases)
    if definition is not None:p=json.loads(Path(definition).read_text(encoding='utf-8'))
    validate_plan(p)
    root.mkdir(parents=True);dump(root/'plan.json',p);(root/'plan.sha256').write_text(sha(root/'plan.json')+'\n')
    (root/'README.md').write_text('计划样例：三次已有灯60技能复用。没有运行手机。\n'
        '证据需由现有采集器产生，放在plan.json指定路径，且case/初态/目标匹配。\n'
        '请在冻结前为实际实验创建适合的计划；此样例的比较元数据为空，不可作为公平A/B。\n'
        '计划锁定后不要改标签或删失败；评分用evaluation_cli.py audit，输出到新目录。\n',encoding='utf-8')
    return p


def audit_to(source,dest):
    source=Path(source).resolve();dest=Path(dest).resolve()
    if dest.exists():raise FileExistsError('Refuse overwriting audit output')
    if dest.is_relative_to(source):raise ValueError('Output must be outside sealed input')
    p,o=audit_campaign(source)
    relatives={relative for case in p['cases'] for relative in case['proof']['files'].values()}
    if (source/'evidence-sha256.json').exists():
        hashes=json.loads((source/'evidence-sha256.json').read_text(encoding='utf-8'))
        if not isinstance(hashes,dict):raise ValueError('Invalid evidence hash manifest')
        relatives.update(hashes)
    evidence=[]
    for relative in relatives:
        if not isinstance(relative,str):raise ValueError('Invalid evidence path')
        origin=(source/relative).resolve();target=(dest/relative).resolve()
        if not origin.is_relative_to(source) or not target.is_relative_to(dest):
            raise ValueError('Evidence path escapes campaign')
        if origin.exists():evidence.append((origin,target))
    dest.mkdir(parents=True)
    for name in ('plan.json','plan.sha256','evidence-sha256.json'):
        if (source/name).exists():shutil.copyfile(source/name,dest/name)
    if (source/'proof').exists():shutil.copytree(source/'proof',dest/'proof')
    # Collectors may keep evidence in run-000 rather than a directory named proof.
    # Copy referenced and sealed files so this exported report can be re-audited.
    for origin,target in evidence:
        if target.exists():continue
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(origin,target)
    return write_report(dest,p,o)


def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='command',required=True)
    cmd=sub.add_parser('import-partial');cmd.add_argument('--source',type=Path,required=True);cmd.add_argument('--output',type=Path,required=True)
    cmd=sub.add_parser('audit');cmd.add_argument('--campaign',type=Path,required=True);cmd.add_argument('--output',type=Path,required=True)
    cmd=sub.add_parser('init');cmd.add_argument('--output',type=Path,required=True);cmd.add_argument('--definition',type=Path)
    cmd=sub.add_parser('compare');cmd.add_argument('--a',type=Path,required=True);cmd.add_argument('--b',type=Path,required=True);cmd.add_argument('--output',type=Path,required=True)
    a=parser.parse_args()
    if a.command=='import-partial':p,o=import_partial(a.source,a.output);r=write_report(a.output,p,o)
    elif a.command=='audit':r=audit_to(a.campaign,a.output)
    elif a.command=='init':create_plan(a.output,a.definition);print('PLAN CREATED; no device task executed');return
    else:
        if a.output.exists():raise FileExistsError('Refuse overwriting comparison')
        r=compare_reports(json.loads(a.a.read_text(encoding='utf-8')),json.loads(a.b.read_text(encoding='utf-8')))
        a.output.parent.mkdir(parents=True,exist_ok=True);dump(a.output,r);print(json.dumps(r,ensure_ascii=True));return
    print(json.dumps(dict(cases=len(r['cases']),stages={k:v['states'] for k,v in r['stages'].items()},alerts=r['alerts']),ensure_ascii=True))


if __name__=='__main__':main()
