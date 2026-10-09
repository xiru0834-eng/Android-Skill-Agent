package edu.sydney.probe;

public final class UiCopyTest {
    public static void main(String[] args) {
        check(UiCopy.selection("invoke",false).equals("已找到对应技能"));
        check(UiCopy.selection("clarify",true).equals("More information needed"));
        check(UiCopy.selection("reject",false).equals("暂不支持这个请求"));
        check(UiCopy.runState("SUCCEEDED",false).equals("上次执行：目标已核验"));
        check(UiCopy.runState("RUNNING",true).equals("Execution in progress"));
        check(!UiCopy.runState("FUTURE_STATUS",true).contains("verified"));
        check(UiCopy.failure("MISSING:wfOpenLamp",false).contains("控件"));
        check(UiCopy.failure("TASK_TIMEOUT",true).contains("time"));
        check(!UiCopy.failure("PRIVATE_DEBUG_TEXT",true).contains("PRIVATE"));
        check(UiCopy.runOutcome("SUCCEEDED",false).equals("目标已核验"));
        check(UiCopy.runOutcome("RUNNING",true).equals("In progress"));
        check(UiCopy.runOutcome("CANCELLED",false).equals("已停止"));
        check(UiCopy.runOutcome("FAILED",true).equals("Not confirmed"));
        check(UiCopy.runOutcome("FUTURE_STATUS",false).equals("未确认完成"));
        check(UiCopy.runOutcome(null,true).equals("Not confirmed"));
        check(contrast(UiStyle.INK,UiStyle.BACKGROUND)>=4.5);
        check(contrast(UiStyle.MUTED,UiStyle.SURFACE)>=4.5);
        check(contrast(UiStyle.SURFACE,UiStyle.ACCENT)>=4.5);
        System.out.println("UiCopyTest: 18 checks passed");
    }
    private static void check(boolean value){if(!value)throw new AssertionError();}
    private static double channel(int c){double v=c/255.0;return v<=0.04045?v/12.92:Math.pow((v+0.055)/1.055,2.4);}
    private static double luminance(int c){return .2126*channel((c>>16)&255)+.7152*channel((c>>8)&255)+.0722*channel(c&255);}
    private static double contrast(int a,int b){double x=luminance(a),y=luminance(b);return (Math.max(x,y)+.05)/(Math.min(x,y)+.05);}
}
