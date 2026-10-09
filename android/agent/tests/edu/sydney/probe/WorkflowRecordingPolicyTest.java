package edu.sydney.probe;

public final class WorkflowRecordingPolicyTest {
    private static int checks;
    private static void eq(Object expected,Object actual){checks++;if(!expected.equals(actual))throw new AssertionError(expected+" != "+actual);}
    public static void main(String[] args){
        WorkflowRecordingPolicy p=new WorkflowRecordingPolicy(0,"before",false);
        eq("WAIT",p.observe(350,null));
        eq("WAIT",p.observe(800,"after"));
        eq("CHANGED",p.observe(1000,"after"));
        p=new WorkflowRecordingPolicy(0,"before",false);
        eq("WAIT",p.observe(350,"before"));
        eq("TIMEOUT",p.observe(1500,"before"));
        p=new WorkflowRecordingPolicy(0,"before",true);
        eq("WAIT",p.observe(100,"before"));
        eq("NOOP",p.observe(350,"before"));
        p=new WorkflowRecordingPolicy(0,"before",true);
        eq("WAIT",p.observe(100,"before"));
        eq("WAIT",p.observe(200,null));
        eq("WAIT",p.observe(250,"before"));
        eq("NOOP",p.observe(450,"before"));
        p=new WorkflowRecordingPolicy(0,"before",false);
        eq("WAIT",p.observe(1400,"after"));
        eq("TIMEOUT",p.observe(1600,"after"));
        p=new WorkflowRecordingPolicy(0,"before",false,4000);
        eq("WAIT",p.observe(2400,"after"));eq("CHANGED",p.observe(2800,"after"));
        eq("TIMEOUT",p.observe(4000,"after"));
        eq(true,WorkflowRecordingPolicy.safeNoop("wfLampValue60",true,"lamp"));
        eq(false,WorkflowRecordingPolicy.safeNoop("wfLampValue60",false,"lamp"));
        eq(false,WorkflowRecordingPolicy.safeNoop("wfLampPower",true,"lamp"));
        eq(false,WorkflowRecordingPolicy.safeNoop("wfLampSave",true,"lamp"));
        eq(false,WorkflowRecordingPolicy.safeNoop("wfLampValue60",true,"fan"));
        eq(true,WorkflowRecordingPolicy.safeNoop("wfMulti",false,"overview"));
        eq("历史技能，与本次录制不同",WorkflowRecordingPolicy.relation("new","old"));
        eq("属于本次录制",WorkflowRecordingPolicy.relation("new","new"));
        eq("暂无",WorkflowRecordingPolicy.relation("new",""));
        System.out.println("WorkflowRecordingPolicyTest: "+checks+" assertions passed");
    }
}
