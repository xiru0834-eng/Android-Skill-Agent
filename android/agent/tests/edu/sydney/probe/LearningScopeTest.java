package edu.sydney.probe;
public final class LearningScopeTest {
    static void check(boolean value){if(!value)throw new AssertionError();}
    static void denied(Runnable fn,String code){try{fn.run();throw new AssertionError("not rejected "+code);}catch(IllegalStateException e){check(e.getMessage().equals(code));}}
    public static void main(String[] args){
        String id="a".repeat(32),obs="b".repeat(32);
        check(LearningScope.validId(id));check(!LearningScope.validId("../x"));check(!LearningScope.validId(null));
        check(LearningScope.allowedPackage("edu.sydney.transferlab"));check(!LearningScope.allowedPackage("com.android.settings"));
        check(LearningScope.safeNavigation("edu.sydney.transferlab","edu.sydney.transferlab:id/wfOpenLamp"));
        check(!LearningScope.safeNavigation("edu.sydney.transferlab","edu.sydney.transferlab:id/wfLampSave"));
        check(!LearningScope.safeNavigation("edu.sydney.transferlab","edu.sydney.transferlab:id/wfLampPower"));
        check(!LearningScope.safeNavigation("edu.sydney.parameterroom","edu.sydney.parameterroom:id/psBrightness"));
        LearningScope s=new LearningScope(id,"edu.sydney.transferlab",10);
        s.observed(obs,11);s.authorize(id,obs,12);check(s.actions==1);
        denied(()->s.authorize(id,obs,13),"STALE_OBSERVATION");
        s.observed(obs,14);denied(()->s.authorize(id,"c".repeat(32),15),"STALE_OBSERVATION");
        denied(()->s.authorize("d".repeat(32),obs,15),"SCOPE_MISMATCH");
        s.observed(obs,15);denied(()->s.authorize(id,obs,2016),"STALE_OBSERVATION");
        s.cancel();denied(()->s.require(id,16),"CANCELLED");
        LearningScope b=new LearningScope(id,"edu.sydney.transferlab",0);
        for(int i=0;i<LearningScope.MAX_ACTIONS;i++){b.observed(obs,i);b.authorize(id,obs,i);}
        b.observed(obs,20);denied(()->b.authorize(id,obs,20),"BUDGET_EXCEEDED");
        LearningScope t=new LearningScope(id,"edu.sydney.transferlab",0);
        denied(()->t.require(id,LearningScope.TOTAL_MS),"BUDGET_EXCEEDED");
        denied(()->t.require(id,-1),"CLOCK_ERROR");
        LearningScope c=new LearningScope(id,"edu.sydney.transferlab",0);
        for(int i=0;i<LearningScope.MAX_CAPTURES;i++)c.capture(id,i);
        denied(()->c.capture(id,100),"BUDGET_EXCEEDED");
        System.out.println("LearningScopeTest PASS (20 assertions/categories)");
    }
}
