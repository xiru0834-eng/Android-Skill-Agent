package edu.sydney.probe;

/** Monotonic deadlines: observing before input must not consume its wait window. */
final class WorkflowTiming {
    private WorkflowTiming() {}
    static void requireBeforeDeadline(long now,long deadline) {
        if(now>=deadline)throw new IllegalStateException("TASK_TIMEOUT");
    }
    static long confirmationDeadline(long dispatchedAt,long deadline) {
        requireBeforeDeadline(dispatchedAt,deadline);
        if(dispatchedAt<0)throw new IllegalArgumentException("NEGATIVE_CLOCK");
        return dispatchedAt+Math.min(3000L,deadline-dispatchedAt);
    }
    static boolean canReportSuccess(long finishedAt,long deadline) {
        return finishedAt<deadline;
    }
    /** A matching read must complete inside both windows, not merely start on time. */
    static void requireConfirmation(long observedAt,long confirmationUntil,long taskDeadline) {
        requireBeforeDeadline(observedAt,taskDeadline);
        if(observedAt>=confirmationUntil)throw new IllegalStateException("STEP_UNCONFIRMED");
    }
}
