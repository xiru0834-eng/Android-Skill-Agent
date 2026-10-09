package edu.sydney.probe;

import java.util.Map;

public final class DemoTraceTest {
    public static void main(String[] args) {
        contentNotificationsAreNotSteps();
        oneClickCreatesOneVerifiedStep();
        identicalCallbackIsMergedButFastSecondClickIsKept();
        missingAndUnchangedValuesStayUnverified();
        orphanStateChangeIsCountedWithoutInventingAClick();
        stepsAreBounded();
        System.out.println("DemoTraceTest passed");
    }

    private static void contentNotificationsAreNotSteps() {
        DemoTrace trace = new DemoTrace();
        trace.setBaseline(Map.of("light", "checked=false"));
        for (int i = 0; i < 4; i++) trace.observeUnattributed(Map.of("light", "checked=false"));
        equal(0, trace.steps().size());
        equal(0, trace.unattributedChanges());
    }

    private static void oneClickCreatesOneVerifiedStep() {
        DemoTrace trace = new DemoTrace();
        trace.setBaseline(Map.of("light", "checked=false"));
        truth(trace.onClick("light", 100));
        trace.completeClick(Map.of("light", "checked=true"));
        equal(1, trace.steps().size());
        equal("checked=false", trace.steps().get(0).before);
        equal("checked=true", trace.steps().get(0).after);
        equal(DemoTrace.Outcome.CHANGED, trace.steps().get(0).outcome);
    }

    private static void identicalCallbackIsMergedButFastSecondClickIsKept() {
        DemoTrace trace = new DemoTrace();
        trace.setBaseline(Map.of("light", "checked=false"));
        truth(trace.onClick("light", 100));
        falsehood(trace.onClick("light", 100));
        truth(trace.onClick("light", 120));
        trace.completeClick(Map.of("light", "checked=false"));
        equal(2, trace.steps().size());
        equal(DemoTrace.Outcome.RAPID_UNCONFIRMED, trace.steps().get(0).outcome);
    }

    private static void missingAndUnchangedValuesStayUnverified() {
        DemoTrace trace = new DemoTrace();
        trace.setBaseline(Map.of("light", "checked=false"));
        truth(trace.onClick("airconPlus", 100));
        trace.completeClick(Map.of("light", "checked=false"));
        equal(DemoTrace.Outcome.UNOBSERVABLE, trace.steps().get(0).outcome);
        truth(trace.onClick("light", 200));
        trace.completeClick(Map.of("light", "checked=false"));
        equal(DemoTrace.Outcome.UNCHANGED, trace.steps().get(1).outcome);
    }

    private static void orphanStateChangeIsCountedWithoutInventingAClick() {
        DemoTrace trace = new DemoTrace();
        trace.setBaseline(Map.of("curtain", "range=0.0"));
        trace.observeUnattributed(Map.of("curtain", "range=50.0"));
        trace.observeUnattributed(Map.of("curtain", "range=50.0"));
        equal(1, trace.unattributedChanges());
        equal(0, trace.steps().size());
        falsehood(trace.onClick("", 100));
        equal(1, trace.unsupportedClicks());
    }

    private static void stepsAreBounded() {
        DemoTrace trace = new DemoTrace();
        trace.setBaseline(Map.of("light", "checked=false"));
        for (int i = 0; i < 30; i++) {
            truth(trace.onClick("light", i + 1));
            trace.completeClick(Map.of("light", "checked=false"));
        }
        falsehood(trace.onClick("light", 31));
        equal(30, trace.steps().size());
    }

    private static void truth(boolean value) { if (!value) throw new AssertionError("expected true"); }
    private static void falsehood(boolean value) { if (value) throw new AssertionError("expected false"); }
    private static void equal(Object expected, Object actual) {
        if (!expected.equals(actual)) throw new AssertionError("expected " + expected + " but got " + actual);
    }
}
