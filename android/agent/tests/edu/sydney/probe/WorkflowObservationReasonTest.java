package edu.sydney.probe;

public final class WorkflowObservationReasonTest {
    public static void main(String[] args){
        int checks=0;
        if(!"WRONG_APP".equals(WorkflowObservationReason.resolve("MISSING:wfReady","OTHER",true)))throw new AssertionError("proven foreign window");checks++;
        for(String owner:new String[]{"APP","CONTROLLER","UNKNOWN",null}){
            if(!"MISSING:wfReady".equals(WorkflowObservationReason.resolve("MISSING:wfReady",owner,true)))throw new AssertionError("unproven owner");checks++;
        }
        if(!"MISSING:wfReady".equals(WorkflowObservationReason.resolve("MISSING:wfReady","OTHER",false)))throw new AssertionError("legacy changed");checks++;
        for(String reason:new String[]{"TASK_TIMEOUT","APPROVAL_CHANGED","INPUT_REJECTED","MISSING:wfFanSave","STALE:wfPage"}){
            if(!reason.equals(WorkflowObservationReason.resolve(reason,"OTHER",true)))throw new AssertionError("unrelated guard changed");checks++;
        }
        if(WorkflowObservationReason.resolve(null,"OTHER",true)!=null)throw new AssertionError("missing cause invented");checks++;
        System.out.println("WorkflowObservationReason: "+checks+" checks passed");
    }
}
