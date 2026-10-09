package edu.sydney.probe;
/** A late network response must not attach to another or cancelled demonstration. */
final class TeachingGuard {
    private long generation;
    private String trace;
    long begin(String raw){trace=raw;return ++generation;}
    void cancel(){generation++;trace=null;}
    boolean accepts(long request,String current){return trace!=null&&generation==request&&trace.equals(current);}
}
