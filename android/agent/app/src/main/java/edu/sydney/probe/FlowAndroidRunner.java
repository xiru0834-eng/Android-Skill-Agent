package edu.sydney.probe;

import android.content.Context;
import android.os.SystemClock;
import org.json.*;
import java.util.*;
import java.util.concurrent.atomic.AtomicBoolean;

/** Whole linear Flow coordinator. The original executor owns every SDK action. */
final class FlowAndroidRunner {
    final FlowTiming timing=new FlowTiming();
    private final JSONObject plan;
    private final PortableSkillCodec.Package pkg;
    private final Set<String> permitted;
    private final String mode,planHash;
    private final JSONArray observations=new JSONArray(),steps=new JSONArray(),actions=new JSONArray();
    private final Map<String,Object> reads=new HashMap<>();
    private JSONObject initial,expected,last;
    private int completed;
    private boolean finalComplete;
    private FlowReviewedBytes localKnowledge;
    private static void need(boolean ok,String code){if(!ok)throw new IllegalArgumentException(code);}
    private static Set<String> strings(JSONArray a)throws Exception{
        Set<String> out=new TreeSet<>();for(int i=0;i<a.length();i++){need(a.get(i) instanceof String,"FLOW_TYPE");need(out.add(a.getString(i)),"FLOW_DUPLICATE");}return out;
    }
    FlowAndroidRunner(JSONObject data,PortableSkillCodec.Package pkg,Set<String> permitted,String mode)throws Exception{
        WorkflowCodec.checkJson(data.toString(),131072);
        plan=new JSONObject(data.toString());this.pkg=pkg;this.permitted=Set.copyOf(permitted);this.mode=mode;
        planHash=PortableSkillCodec.hash(plan.toString());try(var span=timing.span("admission.full_validation")){validate();}
    }
    JSONObject data(){return plan;}
    int budget()throws Exception{return plan.getJSONObject("task_budget").getInt("duration_ms");}
    String hash(){return planHash;}
    void pinLocalPublishedKnowledge(Context context)throws Exception{
        if(!mode.equals("PUBLISHED_USER_TASK"))return;
        var store=new FlowKnowledgeStore(context);String raw=store.approvedRaw();var current=store.decode(raw);
        need(current.getString("flow_hash").equals(plan.getString("flow_hash")),"LOCAL_FLOW_REVIEW_REQUIRED");
        localKnowledge=new FlowReviewedBytes(raw,PortableSkillCodec.hash(raw));
    }
    boolean localKnowledgeCurrent(Context context){
        if(!mode.equals("PUBLISHED_USER_TASK"))return true;
        // The snapshot was fully decoded/validated at admission. Recheck the
        // exact reviewed bytes and live local approval, not a fresh recursive
        // compiler construction on every guard. Change/revocation still stops.
        try(var span=timing.span("guard.local_knowledge_bytes")){return new FlowKnowledgeStore(context).reviewedBytesUnchanged(localKnowledge);}
    }
    private void validate()throws Exception{
        for(String field:List.of("execution_authority","ready_for_device_execution"))need(plan.get(field) instanceof Boolean,"FLOW_TYPE");
        need(plan.get("whole_budget_limit_ms") instanceof Integer&&plan.get("call_count") instanceof Integer,"FLOW_TYPE");
        var budgets=plan.getJSONObject("task_budget");
        for(String field:List.of("duration_ms","max_actions","max_model_calls"))need(budgets.get(field) instanceof Integer,"FLOW_TYPE");
        need(budgets.getInt("max_model_calls")>=0,"FLOW_TYPE");
        need(Set.of("TEST_FIXTURE","CANDIDATE_VALIDATION","PUBLISHED_USER_TASK").contains(mode),"FLOW_MODE");
        need("CompiledFlow".equals(plan.getString("kind"))&&"1.0".equals(plan.getString("version"))&&"COMPILED".equals(plan.getString("status")),"FLOW_NOT_COMPILED");
        need(!plan.getBoolean("execution_authority")&&!plan.getBoolean("ready_for_device_execution"),"SERIALIZED_AUTHORITY_FORBIDDEN");
        need(plan.getJSONArray("blocking_unknowns").length()==0,"BLOCKING_UNKNOWN");
        need(SemanticSkills.registryHash().equals(plan.getString("registry_hash")),"REGISTRY_MISMATCH");
        need(pkg.hash.equals(plan.getString("source_package_raw_hash")),"RAW_APPROVAL_MISMATCH");
        var env=plan.getJSONObject("environment");
        need(PortableSkillCodec.PKG.equals(env.getString("app_package"))&&pkg.appVersion.equals(env.getString("app_version"))&&"ui.u0".equals(env.getString("ui_revision")),"ENVIRONMENT_MISMATCH");
        need(plan.getString("environment_hash").matches("[0-9a-f]{64}"),"ENVIRONMENT_HASH");
        need(budget()>0&&budget()<=8000&&plan.getInt("whole_budget_limit_ms")==8000,"BUDGET_LIMIT_EXCEEDED");
        int max=plan.getJSONObject("task_budget").getInt("max_actions");need(max>=0&&max<=32,"ACTION_BUDGET");
        need(strings(plan.getJSONArray("readable_properties")).equals(pkg.binding.targets.keySet()),"READ_CONTRACT_MISMATCH");
        var rows=plan.getJSONArray("steps");need(rows.length()>0&&rows.length()<=128,"FLOW_STEP_LIMIT");
        Set<String> ids=new HashSet<>(),writes=new TreeSet<>(),availableReads=new HashSet<>();int calls=0;
        validatePredicates(plan.getJSONArray("preconditions"),availableReads);
        for(int i=0;i<rows.length();i++){
            var s=rows.getJSONObject(i);String id=s.getString("id");need(id.matches("[a-zA-Z0-9_.:-]{1,80}")&&ids.add(id),"STEP_ID");
            switch(s.getString("op")){
                case "READ":need(pkg.binding.targets.containsKey(s.getString("target_key")),"UNSUPPORTED_PROPERTY");availableReads.add(id);break;
                case "ASSERT":validatePredicate(s.getJSONObject("predicate"),availableReads);break;
                case "CALL":
                    need(s.get("verify_after_call") instanceof Boolean&&s.get("business_action_retries") instanceof Integer,"FLOW_TYPE");
                    need(++calls<=32,"CALL_LIMIT");String key=s.getString("target_key");need(permitted.contains(key),"UNAUTHORIZED_WRITE");
                    writes.add(key);var value=s.getJSONObject("value");validateValue(value,availableReads);
                    // Check every static CALL before starting any window or business input.
                    Object check=value.getString("kind").equals("literal")?value.get("value"):domainSample(s);
                    var call=pkg.compile(new JSONArray().put(call(s,check))).calls.get(0);
                    need(call.propertyKey().equals(key),"ENTITY_PROPERTY_MISMATCH");
                    need(s.getBoolean("verify_after_call")&&s.getInt("business_action_retries")==0,"FLOW_POLICY_MISMATCH");
                    break;
                default:throw new IllegalArgumentException("UNSUPPORTED_STEP");
            }
        }
        need(calls==plan.getInt("call_count")&&calls<=max,"ACTION_BUDGET");
        need(writes.equals(strings(plan.getJSONArray("actual_write_set"))),"WRITE_SET_MISMATCH");
        need(Collections.disjoint(writes,strings(plan.getJSONArray("must_preserve"))),"CONTRACT_CONFLICT");
        Set<String> preserve=new TreeSet<>(pkg.binding.targets.keySet());preserve.removeAll(writes);
        need(preserve.equals(strings(plan.getJSONArray("preserve_unmentioned"))),"PRESERVATION_CONTRACT");
        validatePredicates(plan.getJSONArray("goals"),availableReads);
    }
    private Object domainSample(JSONObject s)throws Exception{
        String skill=s.getString("skill"),entity=s.getString("entity_id");
        for(int i=0;i<pkg.catalog.length();i++){var e=pkg.catalog.getJSONObject(i);if(e.getString("device").equals(entity)){
            var caps=e.getJSONArray("capabilities");for(int j=0;j<caps.length();j++){var c=caps.getJSONObject(j);if(c.getString("skill").equals(skill)){
                var d=c.getJSONObject("domain");return d.has("values")?d.getJSONArray("values").get(0):d.getInt("min");
            }}
        }}throw new IllegalArgumentException("UNSUPPORTED_CAPABILITY");
    }
    private JSONObject call(JSONObject s,Object value)throws Exception{
        return new JSONObject().put("skill",s.getString("skill")).put("args",new JSONObject().put("device",s.getString("entity_id")).put(s.getString("argument"),value));
    }
    private void validateValue(JSONObject v,Set<String> known)throws Exception{
        switch(v.getString("kind")){
            case "literal":need(v.has("value")&&v.get("value")!=JSONObject.NULL,"UNKNOWN_VALUE");break;
            case "state":case "initial":need(pkg.binding.targets.containsKey(v.getString("key")),"UNSUPPORTED_PROPERTY");break;
            case "read":need(known.contains(v.getString("step_id")),"BAD_READ_REFERENCE");break;
            default:throw new IllegalArgumentException("UNSUPPORTED_VALUE");
        }
    }
    private void validatePredicates(JSONArray list,Set<String> known)throws Exception{
        for(int i=0;i<list.length();i++)validatePredicate(list.getJSONObject(i),known);
    }
    private void validatePredicate(JSONObject p,Set<String> known)throws Exception{
        need(Set.of("known","equals").contains(p.getString("op")),"UNSUPPORTED_PREDICATE");
        if(p.getString("op").equals("known"))validateValue(p.getJSONObject("value"),known);
        else{validateValue(p.getJSONObject("left"),known);validateValue(p.getJSONObject("right"),known);}
    }
    private Object value(JSONObject v,JSONObject state)throws Exception{
        switch(v.getString("kind")){
            case "literal":return v.get("value");
            case "state":return state.get(v.getString("key"));
            case "initial":return initial.get(v.getString("key"));
            case "read":need(reads.containsKey(v.getString("step_id")),"BAD_READ_REFERENCE");return reads.get(v.getString("step_id"));
            default:throw new IllegalArgumentException("UNSUPPORTED_VALUE");
        }
    }
    private static boolean same(Object a,Object b){return a!=null&&b!=null&&a.getClass()==b.getClass()&&a.equals(b);}
    private void predicates(JSONArray list,JSONObject state,String phase)throws Exception{
        for(int i=0;i<list.length();i++){
            var p=list.getJSONObject(i);
            boolean ok=p.getString("op").equals("known")?value(p.getJSONObject("value"),state)!=JSONObject.NULL:
                same(value(p.getJSONObject("left"),state),value(p.getJSONObject("right"),state));
            need(ok,phase+"_FAILED");
        }
    }
    private JSONObject observe(FlowLegacyPort port,String phase)throws Exception{
        try(var span=timing.span("observe."+phase)){var observation=port.observe(phase);observations.put(observation);last=observation.getJSONObject("values");return last;}
    }
    private JSONObject observeStep(FlowLegacyPort port,JSONObject step)throws Exception{
        String op=step.getString("op");if(op.equals("CALL"))return observe(port,step.getString("id"));
        Set<String> properties=new TreeSet<>();
        if(op.equals("READ"))properties.add(step.getString("target_key"));
        else{
            var predicate=step.getJSONObject("predicate");
            for(String field:List.of("value","left","right"))if(predicate.has(field)){
                var expression=predicate.getJSONObject(field);
                if(expression.getString("kind").equals("state"))properties.add(expression.getString("key"));
            }
        }
        // A READ observes its requested property; ASSERT observes its current-
        // state operands. A fresh guarded Root is still read even for historical
        // READ operands. Whole-state checks remain at ENTRY, every CALL, after
        // every CALL and FINAL. Sparse evidence never impersonates a full state.
        try(var span=timing.span("observe."+step.getString("id"))){var observation=port.observe(step.getString("id"),properties);observations.put(observation);
        return observation.getJSONObject("values");}
    }
    private void unchanged(JSONObject actual,JSONObject wanted)throws Exception{
        var keys=actual.keys();while(keys.hasNext()){String key=keys.next();need(same(actual.get(key),wanted.get(key)),"UNEXPECTED_STATE_CHANGE");}
    }
    JSONObject run(Context context,AccessibilityBindingResolver.RootSource source,AtomicBoolean cancelled,long started,java.util.function.BooleanSupplier authorized)throws Exception{
        long deadline=started+budget();timing.deadline(deadline);String status="UNCONFIRMED",reason="";JSONObject result=new JSONObject();
        var gate=new FlowTaskGate(planHash,pkg.hash,plan.getString("environment_hash"),plan.getString("task_id"),plan.getString("host_device_id"),UUID.randomUUID().toString(),permitted,started,deadline,plan.getJSONObject("task_budget").getInt("max_actions"),cancelled,authorized);
        timing.mark("port_open.start");
        try(var port=FlowLegacyPort.open(true,context,source,gate,timing)){
            timing.mark("port_open.end");
            initial=new JSONObject(observe(port,"ENTRY").toString());expected=new JSONObject(initial.toString());
            predicates(plan.getJSONArray("preconditions"),initial,"PRECONDITION");
            var list=plan.getJSONArray("steps");
            for(int i=0;i<list.length();i++){
                var s=list.getJSONObject(i);String id=s.getString("id"),op=s.getString("op");
                timing.mark("step."+op+"."+id+".start");
                var state=observeStep(port,s);unchanged(state,expected);
                var step=new JSONObject().put("id",id).put("op",op).put("status","PENDING");steps.put(step);
                if(op.equals("READ"))reads.put(id,state.get(s.getString("target_key")));
                else if(op.equals("ASSERT"))predicates(new JSONArray().put(s.getJSONObject("predicate")),state,"ASSERTION");
                else{
                    Object wanted=value(s.getJSONObject("value"),state);var raw=new JSONArray().put(call(s,wanted));pkg.compile(raw);
                    JSONObject receipt;try(var span=timing.span("call."+id)){receipt=port.runOne(raw);}step.put("runtime_receipt",receipt);
                    var issued=receipt.getJSONArray("execution_actions");for(int j=0;j<issued.length();j++)actions.put(issued.get(j));
                    need(receipt.getBoolean("verification_result"),"CHILD_"+receipt.getString("final_status")+":"+receipt.getString("reason"));
                    var after=observe(port,"AFTER."+id);var wantedState=new JSONObject(expected.toString());wantedState.put(s.getString("target_key"),wanted);
                    unchanged(after,wantedState);expected=new JSONObject(after.toString());
                }
                step.put("status","VERIFIED");completed++;
                timing.mark("step."+op+"."+id+".end");
            }
            var finalState=observe(port,"FINAL");unchanged(finalState,expected);predicates(plan.getJSONArray("goals"),finalState,"GOAL");
            gate.guard(planHash,pkg.hash,gate.environmentHash,SystemClock.elapsedRealtime());finalComplete=true;
            status=actions.length()==0?"NO_ACTION_REQUIRED":"SUCCESS";
        }catch(Exception e){reason=e.getMessage()==null?e.getClass().getSimpleName():e.getMessage();status=reason.contains("CANCELLED")?"CANCELLED":reason.contains("DEADLINE")?"BUDGET_EXCEEDED":completed>0?"PARTIAL":"UNCONFIRMED";}
        timing.mark("flow_json_assembly.start");
        result.put("flow_scope","WHOLE_LINEAR_FLOW_READ_CALL_ASSERT").put("mode",mode).put("flow_hash",plan.getString("flow_hash")).put("flow_plan_hash",planHash)
            .put("package_hash",pkg.hash).put("task_id",plan.getString("task_id")).put("host_device_id",plan.getString("host_device_id"))
            .put("service_entry_hit",true).put("channel","ANDROID_NATIVE").put("process_session",LearningCapture.PROCESS_SESSION)
            .put("initial_state",initial==null?new JSONObject():initial).put("final_observed_state",last==null?new JSONObject():last)
            .put("final_observation_complete",finalComplete).put("verification_result",finalComplete).put("execution_actions",actions).put("observations",observations)
            .put("steps",steps).put("completed_steps",completed).put("final_status",status).put("reason",reason).put("task_deadline_ms",deadline)
            .put("timing",timing.receipt(plan.getString("task_id"),planHash))
            .put("latency",new JSONObject());
        timing.mark("flow_json_assembly.end");
        finishReceipt(result,started,deadline,cancelled,"FLOW_RECEIPT_BUILT");
        timing.mark("flow_boundary_returned");
        return result;
    }
    static void finishReceipt(JSONObject result,long started,long deadline,AtomicBoolean cancelled,String stage)throws Exception{
        // Use ONE clock sample for both the status decision and its runtime.
        // Receipt construction must not leave an expired SUCCESS on the wire.
        var boundary=new JSONObject().put("stage",stage).put("clock","ELAPSED_REALTIME_MS");
        var latency=result.getJSONObject("latency");String proposed=result.getString("final_status");
        long finished=SystemClock.elapsedRealtime();
        String status=FlowCompletionBoundary.status(proposed,finished,deadline,cancelled.get());
        if(!status.equals(proposed))result.put("final_status",status).put("reason",status.equals("CANCELLED")?"CANCELLED":"TASK_DEADLINE_EXCEEDED")
            .put("verification_result",false).put("final_observation_complete",false);
        boundary.put("finished_ms",finished).put("deadline_ms",deadline).put("proposed_status",proposed).put("final_status",status);
        result.put("completion_boundary",boundary);latency.put("runtime_ms",finished-started);
        if(latency.has("launch_and_runtime_ms"))latency.put("launch_and_runtime_ms",finished-started);
    }
}
