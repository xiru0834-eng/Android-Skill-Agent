package edu.sydney.probe;

/** Local authority expires independently of any network reply. Monotonic time only. */
final class SelectionLease {
    static final int SEMANTIC_MILLIS=21000;
    private final long deadline;
    private final int maximumMillis;
    private volatile boolean cancelled;
    SelectionLease(long nowNanos,int milliseconds){
        this(nowNanos,milliseconds,9000);
    }
    static SelectionLease semantic(long nowNanos){return new SelectionLease(nowNanos,SEMANTIC_MILLIS,SEMANTIC_MILLIS);}
    private SelectionLease(long nowNanos,int milliseconds,int maximum){
        if(milliseconds<=0||milliseconds>maximum)throw new IllegalArgumentException("INVALID_BUDGET");
        maximumMillis=milliseconds;
        deadline=nowNanos+milliseconds*1_000_000L;
    }
    void cancel(){cancelled=true;}
    int remainingMillis(long nowNanos){
        if(cancelled)throw new IllegalArgumentException("SELECTION_CANCELLED");
        long left=deadline-nowNanos;
        if(left<=0)throw new IllegalArgumentException("SELECTION_DEADLINE");
        return (int)Math.min(maximumMillis,(left+999_999L)/1_000_000L);
    }
}
