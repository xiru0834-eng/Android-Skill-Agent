package edu.sydney.probe;

/** Presentation only: an unknown result must never be described as success. */
final class UiCopy {
    private UiCopy(){}
    static String runOutcome(String state,boolean en){
        return switch(state==null?"":state){
            case "SUCCEEDED" -> en?"Targets verified":"目标已核验";
            case "RUNNING" -> en?"In progress":"正在执行";
            case "CANCELLED" -> en?"Stopped":"已停止";
            default -> en?"Not confirmed":"未确认完成";
        };
    }
    static String selection(String state,boolean en){
        return switch(state){
            case "invoke" -> en?"Matching skill found":"已找到对应技能";
            case "clarify" -> en?"More information needed":"还需要补充信息";
            case "reject" -> en?"Request not supported":"暂不支持这个请求";
            default -> en?"Selection not confirmed":"尚未确认选择";
        };
    }
    static String runState(String state,boolean en){
        return switch(state){
            case "SUCCEEDED" -> en?"Last run: targets verified":"上次执行：目标已核验";
            case "RUNNING" -> en?"Execution in progress":"正在执行";
            case "CANCELLED" -> en?"Last run: cancelled":"上次执行：已停止";
            default -> en?"Completion not confirmed":"尚未确认完成";
        };
    }
    static String failure(String code,boolean en){
        if(code==null)code="";
        if(code.startsWith("MISSING:")||code.startsWith("AMBIGUOUS:")||code.contains("BINDING"))return en?"A control could not be identified safely.":"无法可靠定位控件，请检查技能绑定。";
        if(code.contains("TIMEOUT")||code.contains("DEADLINE"))return en?"The result was not confirmed within the time limit.":"未能在时限内确认结果，已停止。";
        if(code.contains("SERVICE"))return en?"Check the accessibility service.":"请检查无障碍服务是否开启。";
        if(code.contains("UNSAVED"))return en?"Save or cancel the App's pending edits first.":"请先保存或取消实验 App 中未保存的修改。";
        if(code.contains("VERSION")||code.contains("INCOMPATIBLE"))return en?"Check the App version and reviewed skill.":"请检查 App 版本与已审核技能是否匹配。";
        if(code.contains("EMPTY_TEXT"))return en?"Enter an instruction first.":"请先输入指令。";
        if(code.contains("TEXT_TOO_LONG"))return en?"Command too long (maximum 500 UTF-16 units). Shorten it; no text was removed.":"指令过长（最多500个UTF-16单元）。请缩短内容；原文没有被删掉。";
        if(code.contains("INVALID_TEXT"))return en?"The command contains an invalid character. Please edit it.":"指令包含无效字符，请修改后重试。";
        if(code.contains("REMOTE_BUSY"))return en?"The previous request is still closing. Please try again shortly.":"上次请求仍在结束，请稍后再试。";
        if(code.contains("SELECTION_CANCELLED"))return en?"Selection cancelled; nothing ran.":"选择已取消，尚未执行。";
        if(code.contains("NO_COMPATIBLE_SKILL"))return en?"Teach or import a compatible skill first.":"请先录制或导入兼容的技能。";
        if(code.contains("SELECTION_CHANGED")||code.contains("STALE"))return en?"The request changed. Please select again.":"请求或页面已变化，请重新选择。";
        return en?"No completion was confirmed. Open details to check the cause.":"尚未确认完成，可在详情中查看原因。";
    }
}
