"""Readable, dated-free report sources and embedded-font PDF rendering."""
import argparse
import json
from pathlib import Path
from xml.sax.saxutils import escape


def proportion(value):
    return '未测' if value['value'] is None else f"{value['numerator']}/{value['denominator']} ({100*value['value']:.1f}%)"


def bounds(value):
    return '未测' if value['wilson95'] is None else f"{100*value['wilson95'][0]:.1f}% 至 {100*value['wilson95'][1]:.1f}%"


def texts(h,summary,regression):
    lang=h['task1'];normal=h['task3']['normalCompletion'];stops=h['task3']['safeStops'];files=summary['evidenceFiles']
    core=f'''# 面向示教流程的 Android GUI 技能复用

论文核心报告 · Xinkai Ru

## 1 研究问题与我的取舍

我希望用户教一次操作后，把完整流程保存成可读、可审核的技能，再在新的设备上复用。当前研究先限定同一个实验App，分开考察同页多控件与跨页有序操作。界面可以改变尺寸和布局，但任务含义与公开控件契约需要明确。

执行时，GPT负责从已保存目录提出技能选择，用户确认后由程序定位控件并执行。模型不直接写批准或任意点击。Demo Probe承担采集、审核、技能库和执行；Transfer Bench是我方构造的可复位实验应用，只改变本地状态。

<!-- flow -->

技能保留页面、对象、动作顺序、期望状态和中间保存，不能压缩为一组最终开关值。例如先把亮度保存为20，再保存为80，两次保存都是流程的一部分；只有最终80正确仍不足以证明复现了示范。

## 2 如何判断一次操作完成

我把流程执行和结果报告分别检查。输入被系统接受不等于目标已经达成；界面到位也可能尚未保存。正常完成要求原技能身份、必要顺序、所有最终目标、非目标保持和截止内确认都正确，还要有延后观察与磁盘证据。

控制器只读取公开GUI信息。独立审计另读实验App账本和持久状态，不把真值反馈给模型或执行器。合理停止与正常完成分开记，缺证明的结果保留为未核实。

<!-- pagebreak -->

## 3 实际完成的工作与证据

第5任务重新接收原始协议、模型回应、执行日志与状态材料，不复制旧报告的成功数。{files}份文本材料保留字节数和SHA256；复制后重新评分，结果一致。原任务2、3、4封存各417、1078、81份文件均未改变。

|阶段|观察到的结果|证据边界|
|---|---|---|
|真实GPT语言选择|180条按原标签正确，60个表达各重复3次|历史v33目录选择；没有本轮新调用|
|任务2源端示教|3条英文流程形成指南并审核保存|全部为自动示范，中文与接收端未验收|
|任务2源端复用|27条过程与状态检查正确|没有逐次磁盘证据；不是迁移27条通过|
|任务3正式正常组|{normal}条完整确认|历史v39；当前v40没有新的设备确认|
|任务3安全组|{stops}条按预期停止，1条原因不符|安全停止不计正常任务完成|
|任务4接收与显示|3条链阻塞，234条执行未运行|安装或导出准备不能当迁移成功|

语言正确率与设备完成率不能合并。180条全部正确的Wilson95下界为{bounds(lang['summary']['passScored']).split(' 至 ')[0]}，也不意味着任意指令都能理解。标签由作者制定，三次重复属于同一表达，并不是180位独立用户。

任务3正式正常组固定126个槽位，只有6条取得完整确认，因此尚不能签收稳定性。跨页5条的执行P50为18.171秒、P95为32.794秒；流程长度不同，准备与审核未包含在内，没有严格性能基线可据此宣称提速。

## 4 测试怎样修正了研究判断

无变化保存的事件在两个同名保存按钮之间无法唯一归因，S6保留9个阻塞槽位。前台切出的一条运行确实停止，但原因与协议不一致，仍判失败。后续v40改了这一有限诊断，没有设备结果证明修复已生效。

软件反例进一步检查磁盘错误、迟到完成、来源索引错误、非目标改变、旧审计复用和缺终态。21条样本均按预期分类，它们证明评估器能区别这些证据问题，不能代替Android实验或运行时消融收益。

<!-- pagebreak -->

## 5 下一项可检验的假设

研究假设是：保持示教流程不变，利用结构化定位和状态核验，可以比固定坐标重放更适应同App显示或布局变化。为此预定三技能、两显示、两布局、三初态，共36对、72次新尝试，两组共用预算、输入权限和独立真值，平衡运行顺序。

原trace没有来源点击坐标，模拟器又连续出现系统无响应，所以基线坐标采集和新设备运行均未完成。不能把旧候选记录与后来补录的坐标组拼成配对。先解决管理入口阻塞，再采集同一来源的真实坐标和公开树证据，冻结后再开始比较。

模型实验另保留同模型三组：无示范逐步操作、带示范上下文逐步操作、示范编译为审核技能后执行。观察和动作能力一致，教学、编译与审核成本另列。实时API测试需要新预算；Jev仅保留为后续目录分类对照。

## 6 可贡献什么，尚不能声称什么

本项目的研究重点是把示教流程的保真、迁移成本、执行核验与失败归因放入同一可复算实验链。当前贡献是具体协议、独立裁判和有保留缺口的证据包；是否优于坐标或逐步模型，尚未证明。

我选择优先保证每个结论能找到原件，而不是把不同版本和不同阶段相加得到一个总成功率。同App显示变化、真实第二台设备、UI契约变化、任意第三方平台属于不同主张，需要分别补证。真人教学与实际公司平台也仍未验收。

## 证据索引

本报告依据T5-EVIDENCE-1、T2-TEACH-1、T3-FLOW-1及T4-TRANSFER-1。本交付中historical.json保存逐例重新判定，input-receipts.json与inputs保存来源和原字节，replication.json保存重新计算结果。详细方法见任务5数据协议；本文为研究阶段报告，不是完成论文或系统发布证明。
'''
    regression_text=('尚未运行本任务最终回归。' if regression is None else
        f"最终离线回归实际运行{regression['pythonMethods']}个Python测试方法、{regression['subtestRecords']}条内部子测试记录；"
        f"失败{regression['pythonFailures']}、错误{regression['pythonErrors']}、跳过{regression['pythonSkipped']}。"
        f"34个Java核心程序通过，测试期间源码稳定。子测试不额外计成设备样本。")
    exp=f'''# GUI 技能复用实验与评估

实验报告 · Xinkai Ru

## 1 本轮到底测试了什么

本轮是主机证据链实验：原件接收、身份与分母检查、独立评分、统计、复制后重算及报告生成。新增手机业务输入0次、远端调用0次。设备结果来自明确版本的历史材料；软件反例和单元方法不进入设备成功率。

计分单位是一条带caseId/runId的完整尝试。正常正确完成、安全负例正确停止、缺证明、环境准备失败和未运行分别记。所有目标与非目标、必要中间保存、持久状态、报告及截止都要核验；SUCCEEDED字符串本身不算通过。

## 2 冻结分母和实际覆盖

|集合|计划|通过|失败|阻塞|未运行|
|---|---|---|---|---|---|
|任务2完整教学|6|3|0|3|0|
|任务2接收端复用|27|0|0|27|0|
|任务2原生反例|24|12|0|0|12|
|任务3同页正常|54|1|0|9|44|
|任务3跨页正常|72|5|0|0|67|
|任务3安全故障|36|22|1|0|13|
|任务3延迟挑战|6|0|0|0|6|
|任务4原包迁移链|3|0|0|3|0|
|任务4正常迁移|216|0|0|0|216|
|任务4绑定负例|18|0|0|0|18|

表内不同集合不相加形成“总准确率”。任务3正常有效评分6/6，与按计划覆盖6/126回答不同问题；前者不能证明剩余条件稳定。源端27条只作任务2同设备背景，不能填入接收端复用。

<!-- pagebreak -->

## 3 语言、耗时与稳定性

历史真实模型为{lang['model']}，使用原5项目录。180条回应按冻结协议重新校验请求、模型身份、回应内容与选择，正例90/90、负例90/90，各90条中文和英文。60个表达均有三次正确结果，标签未由独立用户复核。

|量|重新计算结果|解释|
|---|---|---|
|语言选择正确|{proportion(lang['summary']['passScored'])}|不等于设备完成|
|Wilson95|{bounds(lang['summary']['passScored'])}|固定表达重复，描述性区间|
|选择P50 / P95|{lang['summary']['latencyAll']['p50Ms']/1000:.3f} / {lang['summary']['latencyAll']['p95Ms']/1000:.3f}秒|最近秩，n=180|
|选择最大|{lang['summary']['latencyAll']['maxMs']/1000:.3f}秒|不含手机审核与执行|
|任务2 P / R / V执行P50|3.718 / 5.626 / 6.905秒|各n=9，仅同设备过程检查|
|任务3跨页执行P50 / P95|18.171 / 32.794秒|n=5，版本v39|

以前语言报告采用中位数与插值，P50约2.072秒、P95约3.184秒；原报告不覆盖。本轮最近秩重算略有差异，不是性能改变。没有分段埋点的教学、编译和人工审核耗时保留未测，主机读取时间不替代产品时钟。

原付费账本有180次结算记录，总账约0.643580美元，这是旧账本估计，不是本轮支出或经账单核对的实际扣款。不重发请求、不更新供应商定价、不把剩余额度用于新对照。

## 4 有辨识度的软件反例

|反例族|样本|预期|
|---|---|---|
|完整正常证据|3|PASS|
|最终界面正确而磁盘错误|3|FAIL，误报可被识别|
|完整身份一致但终态过期|3|FAIL，不能靠正确状态过关|
|动作来源索引错误|3|UNVERIFIED|
|非目标被改变|3|FAIL，不能只查目标|
|旧审计重复使用|3|UNVERIFIED|
|缺执行终态收据|3|UNVERIFIED|

21/21符合预期。这是软件裁判敏感性检查，三重复并非独立用户，也不证明21次Android运行成功。实际跳过、联合核验和重新定位的运行时消融还没有完成。

<!-- pagebreak -->

## 5 收发、完整性与封存副本回归

本轮收到{files}份UTF-8材料，每份保存相对路径、字节数与SHA256。严格拒绝重复JSON键、非有限数字、坏编码、超过8MiB文件、路径上跳、链接及已知凭据字段。没有把账户配置或配对凭据加入输入包。

复制后的输入逐文件校验通过，并从全部原始材料重算，历史结果一致。单字节更改、重复ID、错误条件、缺审计、旧成功标志伪装均有测试保护。输出目录必须新建，不覆盖旧失败批次。

|检查|实际结果|
|---|---|
|输入副本校验|{files}/{files}字节与哈希一致|
|完整重新评分|正常6、正确停止22、原原因失败1均保持|
|旧任务2封存|417文件，无缺失/变化/新增|
|旧任务3封存|1078文件，无缺失/变化/新增|
|旧任务4封存|81文件，无缺失/变化/新增|
|新设备对照|72条NOT_RUN，不补历史样本|

{regression_text}

证据链首批的软件夹具缺final及完整状态字段，随后复制校验又将TXT/XML误按JSON读取。两个失败批次保留；修正只在任务5工具和测试中完成。迟到反例也改为保持身份一致，仅检验截止，不把自相矛盾的证据当成可信误报。

这些是证据处理E2E与离线兼容回归。当前v40旧技能设备E2E未运行，不能写成“全部端到端无回归”。

<!-- pagebreak -->

## 6 新对照怎样开展

固定三技能S3/M1/M4，两显示D0/D2，两布局native/reordered，三初态，共36配对72次。保存seed=500731，每组先后顺序总18/18平衡。两组共用60秒截止、24次输入上限、App白名单、相同初态和独立审计，记录原包指纹。

A仅重放真实来源坐标，B执行原结构化技能；不读真值、不改变技能、不因一个组更慢而重启计时。基线坐标尚未采集，系统ANR阻断新运行，因此无配对差值或延迟收益。

主终点是整任务正确完成差值，安全为硬约束；其次看全部尝试及成功/失败/超时耗时、额外输入、观察和适配成本。报告完整配对数、缺失对数、A-only/B-only与精确McNemar双侧p值。36对为探索规模，没有预定确认功效，不据单个p值宣称泛化。

## 7 收尾标准与下一补证动作

软件交付要求原件可追溯、封存副本可重算、坏证据不能洗成PASS、全量离线回归无失败、两PDF字体与分页检查通过。设备签收另要求本版正常与故障矩阵、原技能兼容回归以及显示恢复都有原始证明。

下一步先用现有完整技能库检查管理页ANR和输入就绪，不放宽8秒观察门槛；修复后冻结新版本。随后补v40旧技能回归，再采集公平坐标基线、复核接收端本机审核，运行72次配对。若缺记录、错对象或迟到，停止该批并保留剩余槽位。

当前整体为NOT_READY。真人示范、第二物理手机、契约变化的相似App与公司实际平台分别列为未验收，不由显示测试推断。T5工具提供的是后续每轮实验都能复核的台账和收尾标准。

## 原始材料入口

historical.json为逐例事实；input-receipts.json和inputs为原材料；paired-protocol.json/paired-ledger.json为固定新对照；software-experiment.json和software-raw为软件反例；replication.json为副本重算；protected-before/after为旧封存检查。正文只列核心结果，详细字段见任务5数据协议。
'''
    return core,exp


def create_reports(bundle,regression=None):
    bundle=Path(bundle);summary=json.loads((bundle/'summary.json').read_text(encoding='utf-8'))
    if summary['softwarePipeline']!='PASS':raise ValueError('UNQUALIFIED_EVIDENCE_PIPELINE')
    h=json.loads((bundle/'historical.json').read_text(encoding='utf-8'));reg=None
    if regression:
        reg=json.loads(Path(regression).read_text(encoding='utf-8'))
        if reg['localVerdict']!='PASS' or reg['sourceStable'] is not True or reg['javaCore'] is not True:raise ValueError('REGRESSION_NOT_PASS')
    out=bundle/'reports';out.mkdir(exist_ok=False)
    for name,text in zip(['论文核心报告_Xinkai_Ru','实验报告_Xinkai_Ru'],texts(h,summary,reg)):
        (out/(name+'.md')).write_text(text,encoding='utf-8');render_markdown(text,out/(name+'.pdf'))
    return out


def render_markdown(text,out):
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,PageBreak,Table,TableStyle,Flowable
    from reportlab.pdfgen import canvas
    pdfmetrics.registerFont(TTFont('T5Body','C:/Windows/Fonts/msyh.ttc',subfontIndex=0))
    pdfmetrics.registerFont(TTFont('T5Bold','C:/Windows/Fonts/msyhbd.ttc',subfontIndex=0))
    ink=colors.HexColor('#243444');accent=colors.HexColor('#226A72')
    styles={
        'body':ParagraphStyle('body',fontName='T5Body',fontSize=10.1,leading=17.8,textColor=ink,spaceAfter=9,wordWrap='CJK'),
        'h1':ParagraphStyle('title',fontName='T5Bold',fontSize=22,leading=31,textColor=accent,spaceAfter=16,wordWrap='CJK'),
        'h2':ParagraphStyle('heading',fontName='T5Bold',fontSize=13,leading=21,textColor=accent,spaceBefore=13,spaceAfter=9,keepWithNext=True,wordWrap='CJK'),
        'cell':ParagraphStyle('cell',fontName='T5Body',fontSize=8.5,leading=13,textColor=ink,wordWrap='CJK'),
    }
    class Flow(Flowable):
        def __init__(self):super().__init__();self.width=491;self.height=148
        def draw(self):
            c=self.canv
            boxes=[(0,93,'操作示范','事件 / 控件 / 状态'),(171,93,'形成技能','编译 / 指南 / 审核'),(342,93,'保存与迁移','原包 / 本机再审核'),
                   (342,14,'语言选择','GPT仅提出技能'),(171,14,'程序执行','定位 / 保存 / 限时确认'),(0,14,'独立审计','过程 / 持久状态 / 报告')]
            for x,y,title,sub in boxes:
                c.setFillColor(colors.HexColor('#EEF5F5'));c.setStrokeColor(colors.HexColor('#C1D8DB'));c.roundRect(x,y,149,50,7,fill=1,stroke=1)
                c.setFillColor(accent);c.setFont('T5Bold',10);c.drawCentredString(x+74.5,y+31,title)
                c.setFillColor(ink);c.setFont('T5Body',7.9);c.drawCentredString(x+74.5,y+13,sub)
            c.setStrokeColor(accent);c.setLineWidth(1.1)
            for x1,y1,x2,y2 in [(149,118,171,118),(320,118,342,118),(416,93,416,64),(342,39,320,39),(171,39,149,39)]:
                c.line(x1,y1,x2,y2)
                dx,dy=x2-x1,y2-y1
                if dx>0:c.line(x2,y2,x2-5,y2+3);c.line(x2,y2,x2-5,y2-3)
                elif dx<0:c.line(x2,y2,x2+5,y2+3);c.line(x2,y2,x2+5,y2-3)
                else:c.line(x2,y2,x2-3,y2+5);c.line(x2,y2,x2+3,y2+5)
    story=[];lines=text.splitlines();i=0
    while i<len(lines):
        line=lines[i].strip()
        if not line:i+=1;continue
        if line=='<!-- pagebreak -->':story.append(PageBreak());i+=1;continue
        if line=='<!-- flow -->':story.extend([Flow(),Spacer(1,7)]);i+=1;continue
        if line.startswith('|'):
            table=[]
            while i<len(lines) and lines[i].strip().startswith('|'):
                cells=[s.strip() for s in lines[i].strip().strip('|').split('|')]
                if not all(set(s)<={'-',':'} for s in cells):table.append([Paragraph(escape(s),styles['cell']) for s in cells])
                i+=1
            widths=[491/len(table[0])]*len(table[0]);t=Table(table,colWidths=widths,repeatRows=1,hAlign='LEFT')
            t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#E5F0F0')),('VALIGN',(0,0),(-1,-1),'TOP'),
                ('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7),('TOPPADDING',(0,0),(-1,-1),7),
                ('BOTTOMPADDING',(0,0),(-1,-1),7),('LINEBELOW',(0,0),(-1,0),.8,accent),
                ('LINEBELOW',(0,1),(-1,-1),.3,colors.HexColor('#DFE6E8'))]))
            story.extend([t,Spacer(1,10)]);continue
        key='h1' if line.startswith('# ') else 'h2' if line.startswith('## ') else 'body'
        body=line[2:] if key=='h1' else line[3:] if key=='h2' else line
        story.append(Paragraph(escape(body),styles[key]));i+=1
    def footer(c,doc):
        c.saveState();c.setStrokeColor(colors.HexColor('#D7E1E3'));c.line(52,42,543,42)
        c.setFont('T5Body',8);c.setFillColor(colors.HexColor('#647783'));c.drawString(52,28,'Xinkai Ru  /  GUI 技能复用研究')
        c.drawRightString(543,28,str(doc.page));c.restoreState()
    doc=SimpleDocTemplate(str(out),pagesize=(595.28,841.89),leftMargin=52,rightMargin=52,topMargin=48,bottomMargin=58,
                         title=text.splitlines()[0].lstrip('# '),author='Xinkai Ru')
    def make_canvas(*a,**kw):
        kw['invariant']=1
        return canvas.Canvas(*a,**kw)
    doc.build(story,onFirstPage=footer,onLaterPages=footer,canvasmaker=make_canvas)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--bundle',type=Path,required=True);p.add_argument('--regression',type=Path)
    a=p.parse_args();print(create_reports(a.bundle,a.regression))
