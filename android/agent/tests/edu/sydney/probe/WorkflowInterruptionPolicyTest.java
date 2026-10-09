package edu.sydney.probe;
public final class WorkflowInterruptionPolicyTest {
    public static void main(String[] args){
        check(WorkflowInterruptionPolicy.execution("RUNNING",false),"orphan run not sealed");
        check(!WorkflowInterruptionPolicy.execution("RUNNING",true),"live run sealed");
        for(String state:new String[]{"SUCCEEDED","CANCELLED","UNCONFIRMED","",null})
            check(!WorkflowInterruptionPolicy.execution(state,false),"terminal execution changed");
        check(WorkflowInterruptionPolicy.recording("RECORDING",false),"orphan recording not sealed");
        check(!WorkflowInterruptionPolicy.recording("RECORDING",true),"live recording sealed");
        for(String state:new String[]{"STOPPED","CANCELLED","INTERRUPTED","REJECTED","TIMED_OUT","",null})
            check(!WorkflowInterruptionPolicy.recording(state,false),"terminal recording changed");
        check(WorkflowInterruptionPolicy.validId("e0ca5a72-1956-4ead-99b6-815614f6133c"),"valid identity rejected");
        for(String id:new String[]{"../escape","/absolute",null,"","id.json","E0CA5A72-1956-4EAD-99B6-815614F6133C"})
            check(!WorkflowInterruptionPolicy.validId(id),"unsafe file identity accepted");
        System.out.println("WorkflowInterruptionPolicyTest PASS: orphan sealing, live/terminal preservation, safe identity");
    }
    private static void check(boolean condition,String message){if(!condition)throw new AssertionError(message);}
}
