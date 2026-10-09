package edu.sydney.probe;

public final class WorkflowProfileTest {
    private static int checks;
    private static void equal(long a,long b){checks++;if(a!=b)throw new AssertionError(a+" != "+b);}
    public static void main(String[] args){
        WorkflowProfile p=new WorkflowProfile();
        for(WorkflowProfile.Part part:WorkflowProfile.Part.values())
            for(long value:p.values(part))equal(0,value);
        p.record(WorkflowProfile.Part.SNAPSHOT,20);p.record(WorkflowProfile.Part.SNAPSHOT,7);
        long[] v=p.values(WorkflowProfile.Part.SNAPSHOT);
        equal(2,v[0]);equal(27,v[1]);equal(20,v[2]);
        p.record(WorkflowProfile.Part.INPUT,0);
        equal(1,p.values(WorkflowProfile.Part.INPUT)[0]);equal(0,p.values(WorkflowProfile.Part.JOURNAL)[0]);
        v[1]=999;equal(27,p.values(WorkflowProfile.Part.SNAPSHOT)[1]);
        try{p.record(WorkflowProfile.Part.SNAPSHOT,-1);throw new AssertionError("negative duration accepted");}
        catch(IllegalArgumentException expected){checks++;}
        equal(2,p.values(WorkflowProfile.Part.SNAPSHOT)[0]);
        p.reset();
        for(WorkflowProfile.Part part:WorkflowProfile.Part.values())
            for(long value:p.values(part))equal(0,value);
        System.out.println("WorkflowProfileTest PASS checks="+checks);
    }
}
