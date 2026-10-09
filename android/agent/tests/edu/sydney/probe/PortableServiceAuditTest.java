package edu.sydney.probe;
import java.util.*;
import java.util.concurrent.atomic.AtomicBoolean;

public final class PortableServiceAuditTest {
    static int cases;
    static void check(boolean value){cases++;if(!value)throw new AssertionError("case "+cases);}
    static PortableServiceAudit audit(){return new PortableServiceAudit("task","a".repeat(64),"b".repeat(64),"c".repeat(64),"host","process",100,8000);}
    public static void main(String[] args){
        var a=audit();var r=a.failure("LAUNCH_WAIT","LAUNCH_WINDOW_UNAVAILABLE",8101,false,false,null);
        check(Boolean.TRUE.equals(r.get("service_entry_hit")));check(Boolean.FALSE.equals(r.get("flow_entered")));
        check("task".equals(r.get("task_id")));check("a".repeat(64).equals(r.get("flow_hash")));
        check(!r.containsKey("completion_boundary"));check(Boolean.FALSE.equals(r.get("verification_result")));
        check(((Map<?,?>)r.get("final_observed_state")).isEmpty());
        check("ENVIRONMENT_ERROR".equals(r.get("final_status")));
        check("CANCELLED".equals(a.failure("LAUNCH_WAIT","CANCELLED",110,true,false,null).get("final_status")));
        check(a.failure("FLOW_RUN","err",120,false,true,null).get("execution_actions")==null);
        check(Boolean.FALSE.equals(a.failure("FLOW_RUN","err",120,false,true,null).get("evidence_complete")));
        var partial=new HashMap<String,Object>();partial.put("execution_actions",List.of("REAL_ACTION"));partial.put("completed_steps",2);
        var pr=a.failure("SERIALIZATION","err",130,false,true,partial);
        check(pr.get("execution_actions").equals(List.of("REAL_ACTION")));check(Integer.valueOf(2).equals(pr.get("completed_steps")));
        check(Boolean.FALSE.equals(pr.get("evidence_complete"))); // A partial map is not complete proof.
        for(int i=0;i<256;i++){a.before("windows","launch");a.after("windows","RETURNED");}
        check(((Number)((Map<?,?>)a.counters().get("attempts")).get("windows")).intValue()==256);
        try{a.before("windows","runtime");throw new AssertionError("over cap");}catch(IllegalStateException e){check(e.getMessage().equals("OBSERVATION_BUDGET_EXCEEDED"));}
        var b=audit();b.before("root","launch");b.after("root","FAILED");
        check(((Number)((Map<?,?>)b.counters().get("attempts")).get("root")).intValue()==1);
        var c=audit();c.before("root","launch");
        try{c.before("root","runtime");throw new AssertionError("overlap");}catch(IllegalStateException e){check(e.getMessage().equals("OBSERVATION_CALL_INFLIGHT"));}
        check(((Number)((Map<?,?>)c.counters().get("inflight")).get("root")).intValue()==1);
        var d=audit();try{d.before("screenshot","runtime");throw new AssertionError("screen");}catch(IllegalStateException e){check(e.getMessage().equals("OBSERVATION_BUDGET_EXCEEDED"));}
        AtomicBoolean once=new AtomicBoolean();check(once.compareAndSet(false,true));check(!once.compareAndSet(false,true));
        try{audit().failure("ROOT_READ","err",99,false,false,null);throw new AssertionError("clock");}catch(IllegalStateException e){check(e.getMessage().equals("AUDIT_CLOCK_REGRESSION"));}
        check(Long.valueOf(8100).equals(((Map<?,?>)r.get("error_boundary")).get("deadline_ms")));
        check("VALIDATED_PLAN_DECLARATION".equals(r.get("flow_hash_source")));
        System.out.println("JAVA_PROPOSAL_LOGIC_CASES="+cases+" PASS; NOT_ANDROID_NOT_APPLIED");
    }
}
