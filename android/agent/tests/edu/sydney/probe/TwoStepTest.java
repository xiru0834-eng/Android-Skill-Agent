package edu.sydney.probe;

import java.util.List;
import java.util.Map;

public final class TwoStepTest {
    static final String PKG = ProbePolicy.TRANSFER_PACKAGE;
    static final String A = PKG + ":id/mainToggle", B = PKG + ":id/otherToggle";
    static TwoStepSkill skill() { return new TwoStepSkill(List.of(new SwitchSkill(PKG,A,false,true), new SwitchSkill(PKG,B,false,true))); }
    static TwoStepEngine engine(boolean a, boolean b) { return new TwoStepEngine(skill(), List.of(a,b), 0,3500); }
    static List<ReplayEngine.Scene> scene(boolean a, boolean b) {
        return List.of(new ReplayEngine.Scene(PKG,1,true,a),new ReplayEngine.Scene(PKG,1,true,b));
    }
    static void eq(Object a,Object b) { if (!a.equals(b)) throw new AssertionError(a+" != "+b); }
    public static void main(String[] args) {
        TwoStepEngine e=engine(true,true);
        eq(0,e.observe(scene(false,false),800));
        e.observe(scene(true,false),900); e.observe(scene(true,false),1100);
        eq(1,e.observe(scene(true,false),1200));
        e.observe(scene(true,true),1300); e.observe(scene(true,true),1500);
        eq("RUNNING",e.status); e.observe(scene(true,true),1700);
        eq("SUCCEEDED",e.status); eq(2,e.inputs);
        eq(-2,e.observe(scene(false,false),1800));

        e=engine(true,true); e.observe(scene(false,false),800);
        e.observe(scene(true,false),900); e.observe(scene(true,false),1100);
        eq(1,e.observe(scene(true,false),1200));
        e.observe(scene(false,true),1300);
        eq("UNCONFIRMED",e.status); eq("GOAL_REGRESSED",e.reason); eq(2,e.inputs);

        for(boolean a:new boolean[]{false,true}) for(boolean b:new boolean[]{false,true}) {
            e=engine(a,b);
            for(int t=800;t<2000;t+=100) e.observe(scene(a,b),t);
            eq("SUCCEEDED",e.status); eq(0,e.inputs); eq("ALREADY_AT_TARGETS",e.reason);
        }
        e=engine(true,true); e.observe(scene(false,false),800);
        for(int t=900;t<=3500;t+=100) e.observe(scene(false,false),t);
        eq("DEADLINE",e.reason); eq(1,e.inputs); // No second action while first unconfirmed.
        e=engine(true,true); e.observe(scene(false,false),800);
        e.observe(scene(true,false),3000); e.observe(scene(true,false),3200);
        eq(1,e.observe(scene(true,false),3300));
        e.observe(scene(true,true),3499); e.observe(scene(true,true),3500);
        eq("UNCONFIRMED",e.status); eq("DEADLINE",e.reason); // Shared, not per-step, budget.
        for(int count:new int[]{0,2}) {
            e=engine(true,true);
            e.observe(List.of(new ReplayEngine.Scene(PKG,1,true,false),new ReplayEngine.Scene(PKG,count,true,false)),800);
            eq("REFUSED",e.status); eq(0,e.inputs);
        }
        e=engine(true,true); e.observe(List.of(new ReplayEngine.Scene(PKG,1,true,false),new ReplayEngine.Scene(PKG,1,false,false)),800);
        eq("REFUSED",e.status); eq("UNUSABLE_TARGET",e.reason);
        e=engine(true,true); e.observe(List.of(new ReplayEngine.Scene("other",1,true,false),new ReplayEngine.Scene("other",1,true,false)),800);
        eq("WRONG_APP",e.reason); eq(0,e.inputs);
        e=engine(true,true); e.cancel(100); eq(-2,e.observe(scene(false,false),800)); eq(0,e.inputs);
        e=engine(true,true); e.observe(scene(false,false),800); e.inputRejected(810); eq("INPUT_REJECTED",e.reason);
        e=engine(true,true); e.observe(scene(false,false),800); e.observe(null,900); eq("UNCONFIRMED",e.status);
        e=engine(true,true); e.observe(scene(false,false),3500); eq(0,e.inputs);
        try { new TwoStepSkill(List.of(skill().steps.get(0),skill().steps.get(0))); throw new AssertionError("duplicate"); }
        catch(IllegalArgumentException expected) { }
        try { new TwoStepSkill(List.of(skill().steps.get(0))); throw new AssertionError("count"); }
        catch(IllegalArgumentException expected) { }

        DemoTrace t=new DemoTrace(); t.setBaseline(Map.of(A,"checked=false",B,"checked=false"));
        t.onClick(A,1); t.completeClick(Map.of(A,"checked=true",B,"checked=false"));
        eq("TWO_STEPS_REQUIRED",TwoStepDraft.reason(false,t,PKG));
        t.onClick(B,2); t.completeClick(Map.of(A,"checked=true",B,"checked=true"));
        eq("READY_FOR_REVIEW",TwoStepDraft.reason(false,t,PKG));
        eq(2,TwoStepDraft.compile(false,t,PKG).steps.size());
        eq("RECORDING",TwoStepDraft.reason(true,t,PKG));
        t=new DemoTrace(); t.setBaseline(Map.of(A,"checked=false",B,"checked=false"));
        t.onClick(A,1); t.completeClick(Map.of(A,"checked=true",B,"checked=false"));
        t.onClick(B,2); t.completeClick(Map.of(A,"checked=false",B,"checked=true"));
        eq("FINAL_GOAL_MISMATCH",TwoStepDraft.reason(false,t,PKG));
        t=new DemoTrace(); t.setBaseline(Map.of(A,"checked=false"));
        t.onClick(A,1); t.completeClick(Map.of(A,"checked=true"));
        t.onClick(A,2); t.completeClick(Map.of(A,"checked=false"));
        eq("DISTINCT_TARGETS_REQUIRED",TwoStepDraft.reason(false,t,PKG));
        System.out.println("TwoStepTest passed: sequence, joint regression, parameters, guards, budget, compiler");
    }
}
