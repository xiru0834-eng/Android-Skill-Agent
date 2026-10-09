package edu.sydney.probe;

/** Read-only learning launch budget, distinct from the unchanged 8s business budget. */
final class UserLearningCaptureGate {
    static final long LAUNCH_WAIT_MS = 5000, SESSION_MS = 120000;
    static String decide(long started, long now, boolean armed, String target, String current) {
        if (now < started) return "STOP_CLOCK_ERROR";
        long elapsed = now - started;
        if (elapsed >= SESSION_MS) return "STOP_SESSION_DEADLINE";
        if (!armed) {
            if (elapsed >= LAUNCH_WAIT_MS) return "STOP_LAUNCH_TIMEOUT";
            return target.equals(current) ? "ARM_AND_CAPTURE" : "WAIT_FOR_APP";
        }
        return target.equals(current) ? "CAPTURE" : "STOP_SCOPE_CHANGED";
    }
}
