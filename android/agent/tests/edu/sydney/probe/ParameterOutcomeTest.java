package edu.sydney.probe;
import java.util.*;

public final class ParameterOutcomeTest {
    static int checks;
    static void eq(Object a,Object b){checks++;if(!Objects.equals(a,b))throw new AssertionError(a+" != "+b);}
    public static void main(String[] args){
        var cleanInitial=new FlexibleWorkflow.State("single",new int[]{1,80,1,2});
        eq(false,cleanInitial.complete()); // Legacy replay requires at least one committed step.
        eq(true,ParameterOutcome.canFinish(true,cleanInitial.complete(),true,true));
        eq(false,ParameterOutcome.canFinish(false,cleanInitial.complete(),true,true));
        eq(false,ParameterOutcome.canFinish(true,false,false,true));
        eq(false,ParameterOutcome.canFinish(true,false,true,false));
        eq(true,ParameterOutcome.canFinish(false,true,true,true));
        var on=new SemanticSkills.Call("SetPower","lamp","on");
        var off=new SemanticSkills.Call("SetPower","lamp","off");
        var bright=new SemanticSkills.Call("SetBrightness","lamp",80);
        Map<String,Object> current=Map.of("lamp.power","on","lamp.brightnessPercent",80);
        eq(true,SemanticSkills.allCallsSatisfied(List.of(on,bright),current));
        eq(false,SemanticSkills.allCallsSatisfied(List.of(on,off),current));
        eq(false,SemanticSkills.allCallsSatisfied(List.of(on,bright),Map.of("lamp.power","on")));
        eq(false,SemanticSkills.allCallsSatisfied(List.of(bright),Map.of("lamp.brightnessPercent","80")));
        eq("NO_ACTION_REQUIRED",ParameterOutcome.status("SUCCEEDED","ORDERED_PROCESS_AND_TARGETS_VERIFIED",0));
        eq("SUCCESS",ParameterOutcome.status("SUCCEEDED","ORDERED_PROCESS_AND_TARGETS_VERIFIED",1));
        eq("FAILED",ParameterOutcome.status("UNCONFIRMED","STEP_PRECONDITION_CHANGED",1));
        eq("UNCONFIRMED",ParameterOutcome.status("UNCONFIRMED","STEP_UNCONFIRMED",1));
        eq("REJECTED",ParameterOutcome.status("REJECTED","VALUE_RANGE",0));
        eq("UNCONFIRMED",ParameterOutcome.status("REJECTED","VALUE_RANGE",1));
        eq("validation",ParameterOutcome.stage("VALUE_RANGE",0));
        eq("binding",ParameterOutcome.stage("AMBIGUOUS:wfLampPower",1));
        eq("binding",ParameterOutcome.stage("STALE:wfLampPower",1));
        eq("execution",ParameterOutcome.stage("INPUT_REJECTED",1));
        eq("execution",ParameterOutcome.stage("INPUT_REJECTED",2)); // dispatch enters phase 2 before ACTION_CLICK returns
        eq("verification",ParameterOutcome.stage("STEP_UNCONFIRMED",2));
        eq("verification",ParameterOutcome.stage("FINAL_TARGET_MISMATCH",3));
        eq("parsing",ParameterOutcome.stage("RESPONSE_MISMATCH",0));
        eq("verification",ParameterOutcome.stage("TASK_TIMEOUT",2));
        eq("execution",ParameterOutcome.stage("TASK_TIMEOUT",1));
        eq("UNSUPPORTED_VALUE",ParameterOutcome.safeEntryReason("UNSUPPORTED_VALUE"));
        eq("ENTRY_INVALID",ParameterOutcome.safeEntryReason("private raw user text"));
        eq("REJECTED",ParameterOutcome.entryStatus("UNSUPPORTED_VALUE"));
        eq("UNCONFIRMED",ParameterOutcome.entryStatus("SELECTION_DEADLINE"));
        eq("parsing",ParameterOutcome.stage("SELECTION_DEADLINE",0));
        eq("validation",ParameterOutcome.stage("ENTRY_INVALID",0));
        eq("binding",ParameterOutcome.stage("NO_PARAMETER_SOURCE",0));
        eq("binding",ParameterOutcome.stage("STORAGE_UNCONFIRMED",0));
        eq("binding",ParameterOutcome.stage("SERVICE_OFF",0));
        // A network/interface response is not a user's invalid parameter.
        eq("ENTRY_UNAVAILABLE",ParameterOutcome.entryReason("BRIDGE_HTTP_502",true,"parsing"));
        eq("ENTRY_UNAVAILABLE",ParameterOutcome.entryReason("BRIDGE_HTTP_401",true,"parsing"));
        eq("UNSUPPORTED_VALUE",ParameterOutcome.entryReason("UNSUPPORTED_VALUE",true,"validation"));
        eq("ENTRY_INVALID",ParameterOutcome.entryReason("unknown private input",true,"validation"));
        eq("ENTRY_UNAVAILABLE",ParameterOutcome.entryReason("unknown private network details",false,"parsing"));
        System.out.println("ParameterOutcomeTest passed: "+checks);
    }
}
