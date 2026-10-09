package edu.sydney.probe;

import java.util.List;
import java.util.Map;

public final class TraceBundleTest {
    private static final String PKG=ProbePolicy.TRANSFER_PACKAGE;
    private static final String A=PKG+":id/mainToggle", B=PKG+":id/otherToggle";
    private static final String ID="d66366a8-29a5-4f29-94e1-79cc559c8128";
    private static int checks;
    public static void main(String[] args) {
        DemoTrace trace=normal();
        TraceBundle bundle=capture(trace,"Set both switches on",TraceBundle.End.STOPPED);
        equal("READY_FOR_REVIEW",bundle.candidateReason());
        equal(2,bundle.candidate().steps.size());
        equal(TraceBundle.Source.ADB_TEST,bundle.source);
        equal("checked=false",bundle.steps.get(0).before);
        trace.onClick(A,30);trace.completeClick(Map.of(A,"checked=false",B,"checked=true"));
        equal(2,bundle.steps.size()); // Immutable snapshot, not the live recorder.
        try { bundle.finalState.put(A,"checked=false");throw new AssertionError("mutable"); }
        catch(UnsupportedOperationException expected) { checks++; }
        equal("TASK_GOAL_REQUIRED",capture(normal(),"",TraceBundle.End.STOPPED).candidateReason());
        for(TraceBundle.End end:List.of(TraceBundle.End.RECORDING,TraceBundle.End.INTERRUPTED,TraceBundle.End.TIMED_OUT)) {
            TraceBundle interrupted=capture(normal(),"Turn both on",end);
            equal("RECORDING_NOT_STOPPED",interrupted.candidateReason());equal(null,interrupted.candidate());
        }
        DemoTrace rapid=normal();rapid.onClick(A,30);rapid.onClick(B,31);rapid.abandonPending();
        equal(null,capture(rapid,"Switches",TraceBundle.End.STOPPED).candidate());
        DemoTrace missing=new DemoTrace();missing.onClick(A,1);missing.completeClick(Map.of(A,"checked=true"));
        missing.onClick(B,2);missing.completeClick(Map.of(A,"checked=true",B,"checked=true"));
        equal("UNVERIFIED_STEP",capture(missing,"Switches",TraceBundle.End.STOPPED).candidateReason());
        DemoTrace rollback=normal();rollback.observeUnattributed(Map.of(A,"checked=false",B,"checked=true"));
        equal("INCOMPLETE_TRACE",capture(rollback,"Switches",TraceBundle.End.STOPPED).candidateReason());
        TraceBundle changedFinal=new TraceBundle(ID,PKG,"1", "Switches",TraceBundle.Source.UNKNOWN,
                TraceBundle.End.STOPPED,bundle.steps,Map.of(A,"checked=false",B,"checked=true"),0,0,0);
        equal("FINAL_GOAL_MISMATCH",changedFinal.candidateReason());
        DemoTrace overflow=normal();for(int i=3;i<=31;i++) { overflow.onClick(A,i*10);overflow.completeClick(Map.of(A,"checked=true",B,"checked=true")); }
        equal(1,overflow.overflowClicks());
        equal("INCOMPLETE_TRACE",capture(overflow,"Switches",TraceBundle.End.STOPPED).candidateReason());
        reject(() -> capture(normal(),"x".repeat(241),TraceBundle.End.STOPPED));
        reject(() -> capture(normal(),"private\u0000text",TraceBundle.End.STOPPED));
        reject(() -> new TraceBundle("bad",PKG,"1","Goal",TraceBundle.Source.UNKNOWN,TraceBundle.End.STOPPED,bundle.steps,bundle.finalState,0,0,0));
        reject(() -> new TraceBundle(ID,PKG,"1","Goal",TraceBundle.Source.UNKNOWN,TraceBundle.End.STOPPED,bundle.steps,Map.of("foreign:id/x","checked=true"),0,0,0));
        reject(() -> new TraceBundle(ID,PKG,"1","Goal",TraceBundle.Source.UNKNOWN,TraceBundle.End.STOPPED,bundle.steps,Map.of(A,"range=NaN"),0,0,0));
        System.out.println("TraceBundleTest passed: "+checks+" assertions; bounded evidence, provenance, interruptions and unsafe recovery");
    }
    static DemoTrace normal() {
        DemoTrace t=new DemoTrace();t.setBaseline(Map.of(A,"checked=false",B,"checked=false"));
        t.onClick(A,10);t.completeClick(Map.of(A,"checked=true",B,"checked=false"));
        t.onClick(B,20);t.completeClick(Map.of(A,"checked=true",B,"checked=true"));return t;
    }
    private static TraceBundle capture(DemoTrace t,String goal,TraceBundle.End end) {
        return TraceBundle.capture(ID,PKG,"1",goal,TraceBundle.Source.ADB_TEST,end,t);
    }
    private static void equal(Object a,Object b) { if(!java.util.Objects.equals(a,b)) throw new AssertionError(a+" != "+b);checks++; }
    private static void reject(Runnable action) { try { action.run();throw new AssertionError("accepted invalid evidence"); }catch(IllegalArgumentException expected) { checks++; } }
}
