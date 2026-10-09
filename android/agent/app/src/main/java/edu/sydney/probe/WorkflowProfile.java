package edu.sydney.probe;

/** Per-run, fixed-size counters. Never used to authorize an action. */
final class WorkflowProfile {
    enum Part { SNAPSHOT, TARGET_LOOKUP, INPUT, JOURNAL }
    private final long[][] counters=new long[Part.values().length][3];
    void record(Part part,long elapsedMs){
        if(elapsedMs<0)throw new IllegalArgumentException("NEGATIVE_DURATION");
        long[] v=counters[part.ordinal()];
        v[0]++;v[1]+=elapsedMs;v[2]=Math.max(v[2],elapsedMs);
    }
    long[] values(Part part){return counters[part.ordinal()].clone();}
    void reset(){for(long[] v:counters)java.util.Arrays.fill(v,0);}
}
