package edu.sydney.probe;

import java.util.*;

/** Proposed service audit only. NOT APPLIED to product. No input authority. */
final class PortableServiceAudit {
    private final String task,flow,plan,pkg,host,process;
    private final long started,deadline;
    private final Map<String,Integer> attempts=new LinkedHashMap<>(), inflight=new LinkedHashMap<>();
    private final Map<String,Integer> phases=new LinkedHashMap<>();
    private final List<Map<String,Object>> journal=new ArrayList<>();
    private static final Map<String,Integer> LIMITS=Map.of("windows",256,"root",128,"screenshot",0);
    private long sequence;

    PortableServiceAudit(String task,String flow,String plan,String pkg,String host,String process,long started,long duration){
        if(task==null||task.isEmpty()||host==null||host.isEmpty()||process==null||process.isEmpty()
                ||!hex(flow)||!hex(plan)||!hex(pkg)||started<0||duration<=0||duration>8000)
            throw new IllegalStateException("AUDIT_CONTEXT_INVALID");
        this.task=task;this.flow=flow;this.plan=plan;this.pkg=pkg;this.host=host;this.process=process;
        this.started=started;this.deadline=started+duration;
        for(String k:List.of("windows","root","screenshot")){attempts.put(k,0);inflight.put(k,0);}
    }
    private static boolean hex(String s){return s!=null&&s.matches("[a-f0-9]{64}");}
    synchronized void before(String kind,String phase){
        if(!LIMITS.containsKey(kind)||phase==null||phase.isEmpty())throw new IllegalStateException("AUDIT_COUNTER_INVALID");
        if(inflight.get(kind)>0)throw new IllegalStateException("OBSERVATION_CALL_INFLIGHT");
        if(attempts.get(kind)>=LIMITS.get(kind))throw new IllegalStateException("OBSERVATION_BUDGET_EXCEEDED");
        attempts.put(kind,attempts.get(kind)+1);inflight.put(kind,1);
        String key=phase+":"+kind;phases.put(key,phases.getOrDefault(key,0)+1);
        journal.add(Map.of("seq",++sequence,"event","RESERVED_BEFORE_BINDER","kind",kind,"phase",phase));
    }
    synchronized void after(String kind,String status){
        if(!inflight.containsKey(kind)||inflight.get(kind)!=1)throw new IllegalStateException("AUDIT_COUNTER_UNPAIRED");
        inflight.put(kind,0);journal.add(Map.of("seq",++sequence,"event","BINDER_RETURNED","kind",kind,"status",status));
    }
    synchronized Map<String,Object> counters(){
        var out=new LinkedHashMap<String,Object>();out.put("definition","NATIVE_BINDER_ATTEMPTS_V1");
        out.put("limits",new LinkedHashMap<>(LIMITS));out.put("attempts",new LinkedHashMap<>(attempts));
        out.put("inflight",new LinkedHashMap<>(inflight));out.put("phases",new LinkedHashMap<>(phases));
        out.put("journal",new ArrayList<>(journal));out.put("screen_capture_supported_in_this_path",false);
        return out;
    }
    Map<String,Object> failure(String stage,String reason,long finished,boolean cancelled,boolean entered,Map<String,Object> partial){
        if(finished<started)throw new IllegalStateException("AUDIT_CLOCK_REGRESSION");
        String status=cancelled?"CANCELLED":reason.equals("BLOCKED_BY_OVERLAY")?"BLOCKED_BY_OVERLAY"
            :!entered?"ENVIRONMENT_ERROR":"UNCONFIRMED";
        var out=new LinkedHashMap<String,Object>();
        out.put("receipt_schema","service-failure-v1");out.put("task_id",task);out.put("flow_hash",flow);
        out.put("flow_hash_source","VALIDATED_PLAN_DECLARATION");out.put("flow_plan_hash",plan);out.put("package_hash",pkg);
        out.put("host_device_id",host);out.put("service_entry_hit",true);out.put("process_session",process);out.put("channel","ANDROID_NATIVE");
        out.put("failure_stage",stage);out.put("reason",reason);out.put("flow_entered",entered);
        out.put("final_status",status);out.put("verification_result",false);out.put("final_observation_complete",false);
        List<String> evidence=List.of("initial_state","final_observed_state","execution_actions","observations","completed_steps","steps");
        boolean complete=!entered||partial!=null&&partial.keySet().containsAll(evidence);
        for(String k:evidence){
            Object value=partial==null?null:partial.get(k);
            if(!entered)value=k.equals("completed_steps")?0:k.endsWith("state")?Map.of():List.of();
            out.put(k,value);
        }
        out.put("evidence_complete",complete);out.put("evidence_source",!entered?"NO_FLOW_ENTERED":partial==null?"UNAVAILABLE":"ACTUAL_FLOW_RECEIPT");
        // Null after entry means unknown, not zero inputs/runtime or a guessed state.
        out.put("business_input_count",!entered?0:partial!=null&&partial.get("execution_actions") instanceof Collection<?> c?c.size():null);
        out.put("timing",Map.of("clock","ELAPSED_REALTIME_MS","started_ms",started,"finished_ms",finished));
        out.put("error_boundary",Map.of("stage","SERVICE_ERROR_RECEIPT_READY","clock","ELAPSED_REALTIME_MS",
            "finished_ms",finished,"deadline_ms",deadline,"final_status",status));
        var latency=new LinkedHashMap<String,Object>();latency.put("launch_and_runtime_ms",finished-started);
        latency.put("runtime_ms",entered?null:0);out.put("latency",latency);out.put("observation_budget",counters());
        return out;
    }
}
