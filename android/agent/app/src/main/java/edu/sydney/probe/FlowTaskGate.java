package edu.sydney.probe;

import java.util.Set;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.function.BooleanSupplier;

/** Transient host policy only: not JSON, not stored knowledge, never reloadable. */
final class FlowTaskGate {
    final String planHash,rawPackageHash,environmentHash,taskId,hostDeviceId,sessionId;
    final long startedMs,deadlineMs;
    private final Set<String> allowedWrites;
    private final int maxCalls;
    private final AtomicBoolean cancelled;
    private final BooleanSupplier authorized;
    private boolean claimed,closed;
    private long lastNow;
    private int attempts;

    private static void need(boolean ok,String reason){if(!ok)throw new IllegalStateException(reason);}
    private static boolean hash(String value){return value!=null&&value.matches("[0-9a-f]{64}");}
    private static boolean id(String value){return value!=null&&value.matches("[a-zA-Z0-9_.:-]{1,128}");}
    FlowTaskGate(String plan,String raw,String environment,String task,String host,String session,
                 Set<String> writes,long started,long deadline,int max,AtomicBoolean cancelled,BooleanSupplier authorized){
        need(hash(plan)&&hash(raw)&&hash(environment)&&id(task)&&id(host)&&id(session),"TASK_CONTRACT_ERROR");
        need(writes!=null&&writes.size()<=128&&writes.stream().allMatch(key->key!=null&&key.matches("[a-z][a-z0-9_]{0,63}\\.[A-Za-z][A-Za-z0-9]{0,63}")),"TASK_CONTRACT_ERROR");
        need(started>=0&&deadline>started&&deadline-started<=8000&&max>=0&&max<=32&&cancelled!=null&&authorized!=null,"TASK_CONTRACT_ERROR");
        planHash=plan;rawPackageHash=raw;environmentHash=environment;taskId=task;hostDeviceId=host;sessionId=session;
        allowedWrites=Set.copyOf(writes);startedMs=started;deadlineMs=deadline;maxCalls=max;
        this.cancelled=cancelled;this.authorized=authorized;lastNow=started;
    }
    private void common(String plan,String raw,String environment,long now){
        need(planHash.equals(plan)&&rawPackageHash.equals(raw)&&environmentHash.equals(environment),"TASK_BINDING_MISMATCH");
        need(now>=lastNow&&now>=startedMs,"TASK_CLOCK_ERROR");
        need(!cancelled.get(),"CANCELLED");
        boolean current;
        try{current=authorized.getAsBoolean();}catch(RuntimeException error){throw new IllegalStateException("LOCAL_TASK_POLICY_UNAVAILABLE");}
        need(current,"LOCAL_TASK_AUTHORIZATION_REQUIRED");
        need(now<deadlineMs,"TASK_DEADLINE_EXCEEDED");lastNow=now;
    }
    synchronized void claim(String plan,String raw,String environment,long now){
        need(!claimed&&!closed,"TASK_ALREADY_CLAIMED");common(plan,raw,environment,now);claimed=true;
    }
    synchronized void guard(String plan,String raw,String environment,long now){
        need(claimed&&!closed,"TASK_SESSION_NOT_ACTIVE");common(plan,raw,environment,now);
    }
    synchronized void authorizeCall(String key,String plan,String raw,String environment,long now){
        guard(plan,raw,environment,now);need(allowedWrites.contains(key),"UNAUTHORIZED_WRITE");
        need(attempts<maxCalls,"ACTION_BUDGET_EXCEEDED");attempts++;
    }
    synchronized int calls(){return attempts;}
    synchronized void close(){closed=true;}
}
