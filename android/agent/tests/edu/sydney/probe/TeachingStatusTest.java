package edu.sydney.probe;

public final class TeachingStatusTest {
    static int checks;
    static void eq(Object expected,Object actual){checks++;if(!expected.equals(actual))throw new AssertionError(expected+" != "+actual);}
    public static void main(String[] args){
        TeachingStatus.Data d=new TeachingStatus.Data();d.connected=true;
        eq("IDLE",TeachingStatus.kind(d));
        d.preparing=true;eq("PREPARING",TeachingStatus.kind(d));eq(false,TeachingStatus.canStart(d));d.preparing=false;
        d.end="REJECTED";d.error="OLD_FAILURE";eq("IDLE",TeachingStatus.kind(d));
        d.selected=true;eq("ERROR",TeachingStatus.kind(d));
        d.active=true;d.ready=false;eq("PREPARING",TeachingStatus.kind(d));
        d.ready=true;eq("RECORDING",TeachingStatus.kind(d));
        d.pending=true;eq("CONFIRMING",TeachingStatus.kind(d));
        d.pending=false;d.inspecting=true;eq("INSPECTING",TeachingStatus.kind(d));
        d.active=false;d.inspecting=false;d.end="CANCELLED";eq("CANCELLED",TeachingStatus.kind(d));
        d.end="STOPPED";d.error="";d.steps=7;d.savedOverview=true;eq("INCOMPLETE",TeachingStatus.kind(d));
        d.flexible=true;eq("ENDED",TeachingStatus.kind(d));
        d.steps=2;eq("ENDED",TeachingStatus.kind(d));
        d.steps=0;eq("INCOMPLETE",TeachingStatus.kind(d));
        d.flexible=false;
        d.steps=8;eq("ENDED",TeachingStatus.kind(d));
        d.steps=4;eq("ENDED",TeachingStatus.kind(d));
        d.routeValid=false;eq("INCOMPLETE",TeachingStatus.kind(d));d.routeValid=true;
        eq(true,TeachingStatus.hint("ENDED","",4,false).contains("4"));
        d.steps=8;
        d.savedOverview=false;eq("INCOMPLETE",TeachingStatus.kind(d));
        d.savedOverview=true;d.connected=false;eq("ENDED",TeachingStatus.kind(d));
        d.selected=false;eq("DISCONNECTED",TeachingStatus.kind(d));
        d.selected=true;d.busy=true;eq("GENERATING",TeachingStatus.kind(d));
        d.busy=false;d.draft=true;eq("REVIEW",TeachingStatus.kind(d));
        d.saved=true;eq("SAVED",TeachingStatus.kind(d));
        eq("01:05",TeachingStatus.clock(65000));
        eq("00:00",TeachingStatus.clock(-4));
        eq(true,TeachingStatus.title("RECORDING",false).contains("正在录制"));
        eq(true,TeachingStatus.title("ENDED",false).contains("已结束"));
        eq(true,TeachingStatus.hint("ENDED","",8,false).contains("尚未保存技能"));
        eq(false,TeachingStatus.canGenerate("INCOMPLETE"));
        eq(true,TeachingStatus.canGenerate("ENDED"));
        TeachingStatus.Data wrong=new TeachingStatus.Data();wrong.selected=true;wrong.end="STOPPED";wrong.steps=8;wrong.savedOverview=true;wrong.routeValid=false;
        eq("INCOMPLETE",TeachingStatus.kind(wrong));
        eq(true,TeachingStatus.error("OVERLAPPING_INPUT",false).contains("未确认"));
        eq(false,TeachingStatus.error("NEW_UNKNOWN_ERROR",false).contains("NEW_UNKNOWN_ERROR"));
        TeachingStatus.Data gate=new TeachingStatus.Data();
        eq(false,TeachingStatus.canStart(gate));gate.connected=true;eq(true,TeachingStatus.canStart(gate));
        gate.active=true;eq(false,TeachingStatus.canStart(gate));gate.active=false;gate.busy=true;eq(false,TeachingStatus.canStart(gate));
        gate.busy=false;gate.running=true;eq(false,TeachingStatus.canStart(gate));
        eq(true,TeachingStatus.error("TIMED_OUT",false).contains("预算"));
        for(String state:new String[]{"IDLE","DISCONNECTED","PREPARING","RECORDING","CONFIRMING","INSPECTING","ENDED","INCOMPLETE","CANCELLED","ERROR","GENERATING","REVIEW","SAVED","RUNNING"}){
            eq(false,TeachingStatus.title(state,true).isBlank());eq(false,TeachingStatus.hint(state,"",0,true).isBlank());
        }
        System.out.println("TeachingStatusTest: "+checks+" assertions passed");
    }
}
