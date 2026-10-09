package edu.sydney.probe;

public final class WorkflowPreparationPolicyTest {
    private static int checks;
    private static void eq(Object want,Object got){checks++;if(!want.equals(got))throw new AssertionError(want+" != "+got);}
    public static void main(String[] args){
        WorkflowPreparationPolicy record=new WorkflowPreparationPolicy(0,"");
        eq("STABILIZING",record.observe(0,"single",false,"one"));
        eq("STABILIZING",record.observe(249,"single",false,"one"));
        eq("READY",record.observe(250,"single",false,"one"));
        eq(true,record.mayStart(251,"single",false,"one"));
        eq(false,record.mayStart(251,"single",true,"one"));
        eq(false,record.mayStart(251,null,false,"one"));
        eq(false,record.mayStart(251,"single",false,null));
        eq("UNSAVED",record.observe(300,"single",true,"dirty"));
        eq("STABILIZING",record.observe(400,"single",false,"one"));
        eq("READY",record.observe(650,"single",false,"one"));
        eq(false,record.mayStart(651,"single",false,"new"));
        eq("RETURN_OVERVIEW",record.observe(700,"lamp",false,"lamp"));
        eq("UNSAVED",record.observe(800,"fan",true,"fan-dirty"));
        eq("WAIT",record.observe(900,null,false,null));
        eq("WAIT",record.observe(1000,"unknown",false,"unknown"));
        WorkflowPreparationPolicy pages=new WorkflowPreparationPolicy(0,"overview");
        eq("SWITCH_PAGES",pages.observe(0,"single",false,"one"));
        eq("UNSAVED",pages.observe(100,"single",true,"one"));
        eq("STABILIZING",pages.observe(200,"overview",false,"two"));
        eq("READY",pages.observe(450,"overview",false,"two"));
        eq(false,pages.mayStart(451,"single",false,"one"));
        WorkflowPreparationPolicy single=new WorkflowPreparationPolicy(0,"single");
        eq("SWITCH_SINGLE",single.observe(0,"overview",false,"two"));
        eq("RETURN_OVERVIEW",single.observe(100,"fan",false,"fan"));
        eq("TIMED_OUT",single.observe(60000,"single",false,"one"));
        eq(false,single.mayStart(60000,"single",false,"one"));
        pages.cancel();eq("CANCELLED",pages.observe(500,"overview",false,"two"));
        eq(false,pages.mayStart(501,"overview",false,"two"));
        for(String page:new String[]{"single","overview"}){
            WorkflowPreparationPolicy p=new WorkflowPreparationPolicy(100,"");
            eq("STABILIZING",p.observe(100,page,false,"same"));
            eq("READY",p.observe(350,page,false,"same"));
            eq("WAIT",p.observe(400,null,false,null));
            eq(false,p.mayStart(401,page,false,"same"));
        }
        System.out.println("WorkflowPreparationPolicyTest passed: "+checks);
    }
}
