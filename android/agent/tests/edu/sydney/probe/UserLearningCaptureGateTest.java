package edu.sydney.probe;

/** Pure launch/capture policy tests. No Android operation or actual UI proof. */
public final class UserLearningCaptureGateTest {
    private static int checks;
    private static void is(String expected, String actual) {
        checks++;
        if (!expected.equals(actual)) throw new AssertionError(expected + " != " + actual);
    }
    public static void main(String[] args) {
        String target = "approved.app";
        is("WAIT_FOR_APP", UserLearningCaptureGate.decide(100, 100, false, target, "probe"));
        is("WAIT_FOR_APP", UserLearningCaptureGate.decide(100, 5099, false, target, "launcher"));
        is("ARM_AND_CAPTURE", UserLearningCaptureGate.decide(100, 4999, false, target, target));
        is("STOP_LAUNCH_TIMEOUT", UserLearningCaptureGate.decide(100, 5100, false, target, "probe"));
        is("STOP_LAUNCH_TIMEOUT", UserLearningCaptureGate.decide(100, 5100, false, target, target));
        is("CAPTURE", UserLearningCaptureGate.decide(100, 119999, true, target, target));
        is("STOP_SCOPE_CHANGED", UserLearningCaptureGate.decide(100, 1000, true, target, "external"));
        is("STOP_SCOPE_CHANGED", UserLearningCaptureGate.decide(100, 1000, true, target, "probe"));
        is("STOP_SCOPE_CHANGED", UserLearningCaptureGate.decide(100, 1000, true, target, ""));
        is("STOP_SESSION_DEADLINE", UserLearningCaptureGate.decide(100, 120100, true, target, target));
        is("STOP_SESSION_DEADLINE", UserLearningCaptureGate.decide(100, 120100, false, target, target));
        is("STOP_CLOCK_ERROR", UserLearningCaptureGate.decide(100, 99, false, target, target));
        System.out.println("UserLearningCaptureGateTest PASS " + checks + " launch/scope/shared-deadline checks; no Android proof");
    }
}
