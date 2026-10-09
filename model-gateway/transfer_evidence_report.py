"""Build transparent descriptive tables and failure cards from closed batches.

This postprocessor cannot edit a terminal, oracle, or primary score. Repeat
trials are described as repeated executions of one skill, never new skills.
"""
import argparse
import json
import statistics
from pathlib import Path
from transfer_protection import assess,late_effects
from workflow_experiment import write


def load(path):return json.loads(path.read_text(encoding='utf-8'))


def summarize(folder):
    protocol=load(folder/'protocol.json');audit=load(folder/'reaudit.json')
    audited={r['run']:r for r in audit['rows']};groups={};cards=[]
    for index,case in enumerate(protocol['cases']):
        run=folder/f'run-{index:03d}';key=case.get('condition',case.get('initialId',case['fault']))
        group=groups.setdefault(key,dict(planned=0,scored=0,confirmed=0,false_success=0,unconfirmed_success=0,
            unknown=0,not_run=0,success_ms=[],failure_ms=[],ui_success_ms=[],ui_failure_ms=[],inputs=[],observations=[],reasons={},protection_pass=0,
            protection_tested=0,positive_challenge_pass=0,trigger_observed=0,input_mismatch=0,late_app_inputs=0,late_effect_trials=0,late_effect_events=0))
        group['planned']+=1
        if not run.exists():group['not_run']+=1;continue
        if not (run/'score.json').exists():
            group['unknown']+=1
            failure=load(run/'failure.json') if (run/'failure.json').exists() else {}
            cards.append(dict(run=str(run),condition=key,classification='证据不足',first_error=None,
                              expected=load(folder/'skill.json')['finalGoals'],reason=failure.get('infrastructureFailure','未形成完整终态'),
                              evidence=[str(p) for p in sorted(run.glob('*.json'))]))
            continue
        score=load(run/'score.json');terminal=load(run/'terminal.json');oracle=load(run/'oracle.json');journal=load(run/'journal.json')
        verification=audited[run.name]
        if not verification.get('auditable'):raise ValueError('Missing recomputed score: '+str(run))
        for metric in ('confirmed','false_success'):
            if verification[metric]!=score['confirmed_success' if metric=='confirmed' else metric]:raise ValueError('Audit mismatch')
        group['scored']+=1;group['confirmed']+=score['confirmed_success'];group['false_success']+=score['false_success']
        group['unconfirmed_success']+=score['unconfirmed_success']
        group['success_ms' if score['confirmed_success'] else 'failure_ms'].append(score['elapsed_ms'])
        group['ui_success_ms' if score['confirmed_success'] else 'ui_failure_ms'].append(score['ui_completion_ms'])
        group['inputs'].append(score['inputs']);group['observations'].append(terminal['observations'])
        reason=terminal['reason'];group['reasons'][reason]=group['reasons'].get(reason,0)+1
        group['input_mismatch']+=not verification['actualInputsMatchRequested'];group['late_app_inputs']+=verification['lateAppInputs']
        delayed=late_effects(oracle,terminal['finishedMs']);group['late_effect_trials']+=bool(delayed);group['late_effect_events']+=len(delayed)
        challenge=assess(case,terminal,oracle,score,verification)
        if challenge['protection_pass'] is not None:
            group['protection_tested']+=1;group['protection_pass']+=challenge['protection_pass']
        group['trigger_observed']+=bool(challenge['trigger_observed']);group['positive_challenge_pass']+=bool(challenge['positive_challenge_pass'])
        if not score['confirmed_success']:
            errors=[e for e in journal if e['kind']=='ERROR']
            cards.append(dict(run=str(run),condition=key,classification='误报成功' if score['false_success'] else '未完成或未确认',
                expected=terminal['goal'],actual=score['terminal_saved'],reason=reason,
                first_error=errors[0] if errors else None,terminal_step=terminal['completedSteps'],
                challenge=challenge,late_effects=delayed,root_cause='尚需结合观察与 App 事件解释；首条异常不自动等于根因',
                evidence=[str(run/n) for n in ('case.json','before.json','journal.json','terminal.json','oracle.json','audit.json','score.json')]))
    for group in groups.values():
        times=group['success_ms'];group['success_median_ms']=statistics.median(times) if times else None
        group['success_range_ms']=[min(times),max(times)] if times else None
        group['ui_success_median_ms']=statistics.median(group['ui_success_ms']) if group['ui_success_ms'] else None
    return dict(batch=str(folder),planned=len(protocol['cases']),device=protocol['device'],groups=groups,
                audit_complete=audit['complete'],non_target_metric='N/A: all four fields are task targets',failure_cards=cards)


def main():
    p=argparse.ArgumentParser();p.add_argument('directories',type=Path,nargs='+');p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=False);reports=[summarize(f) for f in a.directories]
    write(a.output/'evidence-summary.json',reports)
    text=['# 固定技能迁移：逐组结果','',
          '本表来自持久化原始记录及独立重算。同一技能的重复执行不是多个独立技能。正常任务完成、故障下保护停止和证据不足分开报告。非目标误改指标为 N/A；不以空集合声称零误改。','']
    for report in reports:
        text += ['## '+Path(report['batch']).name,'',
                 '| 条件 | 计划 | 已评分 | 正确完成 | 误报 | 已完成未确认 | 证据不足 / 未运行 | 成功耗时中位数（ms） | 保护符合 |',
                 '|---|---:|---:|---:|---:|---:|---:|---:|---:|']
        for key,g in report['groups'].items():
            protection=f"{g['protection_pass']}/{g['protection_tested']}" if g['protection_tested'] else 'N/A'
            text.append(f"| {key} | {g['planned']} | {g['scored']} | {g['confirmed']} | {g['false_success']} | {g['unconfirmed_success']} | {g['unknown']} / {g['not_run']} | {g['success_median_ms'] if g['success_ms'] else 'N/A'} | {protection} |")
        text += ['',f"证据目录：`{report['batch']}`。原始耗时点、失败耗时、输入次数、具体错误码及触发证据见 evidence-summary.json。",'']
    text += ['## 失败卡','']
    for report in reports:
        for card in report['failure_cards']:
            text += ['### '+Path(report['batch']).name+'/'+Path(card['run']).name+' · '+card['condition'],'',
                     '- 分类：'+card['classification'],
                     '- 程序终态：'+card.get('reason','无完整终态'),
                     '- 期望 / 最终已提交：'+str(card.get('expected','未知'))+' / '+str(card.get('actual','未知')),
                     '- 首条观察异常：'+json.dumps(card['first_error'],ensure_ascii=False),
                     '- 原始证据：`'+card['run']+'`','']
    (a.output/'tables-and-failures.md').write_text('\n'.join(text)+'\n',encoding='utf-8')
    print(json.dumps(dict(batches=len(reports),planned=sum(r['planned'] for r in reports),failure_cards=sum(len(r['failure_cards']) for r in reports))))


if __name__=='__main__':main()
