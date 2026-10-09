package edu.sydney.probe;
public final class WorkflowResolutionReasonTest {
    public static void main(String[] args){
        String[] input={"MISSING_TARGET","AMBIGUOUS_ID","AMBIGUOUS_TARGET","TARGET_DISABLED","UNUSABLE_TARGET","TARGET_STATE_CHANGED","TASK_TIMEOUT"};
        String[] expected={"MISSING:wfLampSave","AMBIGUOUS:wfLampSave","AMBIGUOUS:wfLampSave","NOT_CLICKABLE","UNUSABLE:wfLampSave","TARGET_STATE_CHANGED","TASK_TIMEOUT"};
        for(int i=0;i<input.length;i++)if(!expected[i].equals(WorkflowResolutionReason.translate(input[i],"wfLampSave")))throw new AssertionError(input[i]);
        System.out.println("WorkflowResolutionReasonTest PASS 7 compatibility checks");
    }
}
