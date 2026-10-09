package edu.sydney.parameterroom;
/** Test-environment scheduling token; old tasks cannot commit into a new fixture. */
final class DeferredCommit {
    final long dueAt;final int generation;
    DeferredCommit(int generation,long issuedAt,int delayMs){
        if(delayMs<0||delayMs>20000)throw new IllegalArgumentException("COMMIT_DELAY_RANGE");
        this.generation=generation;dueAt=issuedAt+delayMs;
    }
    boolean ready(int activeGeneration,long now){return generation==activeGeneration&&now>=dueAt;}
    /** -1 cancels stale work; 0 commits; positive values must be rescheduled. */
    long remainingDelay(int activeGeneration,long now){
        return generation!=activeGeneration?-1:Math.max(0,dueAt-now);
    }
}
