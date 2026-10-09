package edu.sydney.probe;
import java.util.*;
public final class WorkflowAttributionTest {
    static int checks;
    static void yes(boolean b){checks++;if(!b)throw new AssertionError("check "+checks);}
    static String resolve(FlexibleWorkflow.State before,List<String> ids,FlexibleWorkflow.State after){
        return FlexibleWorkflow.resolve(before,ids,after.page(),after.values(),after.saved(),after.dirty());
    }
    public static void main(String[] args){
        var before=new FlexibleWorkflow.State("single",new int[]{0,40,0,3});
        var after=before.copy();after.apply("wfLampPower",true);
        yes(resolve(before,List.of("wfLampPower","wfFanPower"),after).equals("wfLampPower"));
        yes(!before.dirty());
        yes(resolve(before,List.of("wfLampPower","wfLampPower"),after).isEmpty());
        yes(resolve(before,List.of("wfFanPower","foreign"),after).isEmpty());
        var both=after.copy();both.apply("wfFanPower",true);
        yes(resolve(before,List.of("wfLampPower","wfFanPower"),both).isEmpty());
        var saved=after.copy();saved.apply("wfLampSave",null);
        yes(resolve(after,List.of("wfLampSave","wfFanSave"),saved).equals("wfLampSave"));
        yes(resolve(saved,List.of("wfLampSave","wfFanSave"),saved).isEmpty());
        System.out.println("WorkflowAttributionTest: "+checks+" assertions passed");
    }
}
