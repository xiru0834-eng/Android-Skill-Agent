package edu.sydney.probe;

/** Fixed read-only observation budget, independent of business input/task budgets. */
final class ReadOnlyObservationRetry {
    static final int MAX_ATTEMPTS=4;
    static final long TOTAL_BUDGET_MS=2500;
    private ReadOnlyObservationRetry(){}
    static boolean retry(String reason,int completedAttempts,long now,long deadline){
        return completedAttempts>=1&&completedAttempts<MAX_ATTEMPTS&&now>=0&&now<deadline
            &&PortableObservationPolicy.retryObservation(reason);
    }
    static long delay(long now,long deadline){return Math.min(80,Math.max(0,deadline-now));}
    static void requireCurrent(long now,long deadline){
        if(now<0||now>=deadline)throw new IllegalStateException("AUDIT_TIMEOUT");
    }
}
