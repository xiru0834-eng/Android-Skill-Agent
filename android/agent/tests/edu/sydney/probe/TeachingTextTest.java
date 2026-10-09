package edu.sydney.probe;
public final class TeachingTextTest {
    public static void main(String[] args) {
        if(!TeachingText.recordOrigin("AUTOMATED",false).contains("不是你的新示范"))throw new AssertionError("automated provenance");
        if(!TeachingText.recordOrigin("AUTOMATED",true).contains("Automated"))throw new AssertionError("English provenance");
        if(!TeachingText.recordOrigin("HUMAN_DECLARED",false).contains("示范记录"))throw new AssertionError("declared provenance");
        if(!TeachingText.step("wfLampPower",false,false).contains("关闭"))throw new AssertionError("off");
        if(!TeachingText.step("wfLampValue80",true,true).contains("80%"))throw new AssertionError("value");
        if(!TeachingText.step("wfFanValue3",true,false).contains("高档"))throw new AssertionError("speed");
        if(!TeachingText.step("wfFanSave",null,true).contains("Save"))throw new AssertionError("commit");
        String single=TeachingText.observed("wfLampSave",null,"single",false);
        if(!single.contains("单页")||single.contains("返回总览"))throw new AssertionError("single save fabricated navigation");
        if(!TeachingText.observed("wfLampSave",null,"single",true).contains("lamp")||!TeachingText.observed("wfFanSave",null,"single",true).contains("fan"))throw new AssertionError("guide omitted save target identity");
        if(!TeachingText.observed("wfFanSave",null,"overview",true).contains("overview"))throw new AssertionError("cross-page save");
        if(!TeachingText.observed("wfLampCancel",null,"single",true).contains("single"))throw new AssertionError("single cancel");
        if(!TeachingText.observed("wfLampPower",false,"single",false).equals(TeachingText.step("wfLampPower",false,false)))throw new AssertionError("ordinary step changed");
        try {TeachingText.observed("wfLampSave",null,"unknown",true);throw new AssertionError("unknown page accepted");}
        catch(IllegalArgumentException expected){}
        if(!TeachingText.recordState("CANCELLED",false).contains("取消"))throw new AssertionError("cancel label");
        if(!TeachingText.recordState("STOPPED",true).contains("Finished"))throw new AssertionError("finished label");
        try {TeachingText.step("wfReset",null,false);throw new AssertionError("unknown accepted");}
        catch(IllegalArgumentException expected){}
        TeachingGuard guard=new TeachingGuard();long first=guard.begin("trace-a");
        if(!guard.accepts(first,"trace-a"))throw new AssertionError("current");
        if(guard.accepts(first,"trace-b"))throw new AssertionError("trace changed");
        guard.cancel();if(guard.accepts(first,"trace-a"))throw new AssertionError("cancel");
        long second=guard.begin("trace-b");
        if(guard.accepts(first,"trace-a")||!guard.accepts(second,"trace-b"))throw new AssertionError("late response");
        System.out.println("PASS TeachingTextTest: bilingual guide, unknown action, stale and cancelled responses");
    }
}
