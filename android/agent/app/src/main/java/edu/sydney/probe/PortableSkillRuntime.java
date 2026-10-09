package edu.sydney.probe;
import android.os.SystemClock;
import android.graphics.Rect;
import org.json.*;
import java.util.*;
import java.util.function.BooleanSupplier;

/** Current-tree execution; no ADB, private oracle, coordinate replay, model request or implicit retry. */
final class PortableSkillRuntime {
    private final AccessibilityBindingResolver.RootSource source;
    private final BooleanSupplier cancelled;
    private final PortableSkillCodec.Package pkg;
    private long deadline,resolveMs,inputMs,verifyMs;
    private final JSONArray resolved=new JSONArray(),actions=new JSONArray(),observations=new JSONArray();
    private final JSONArray recovery=new JSONArray();
    private Map<String,Object> last=Map.of(),initial=Map.of();
    private boolean lastComplete;
    interface InputDispatcher {boolean dispatch(AccessibilityBindingResolver.Resolved target,String skill,Object value,long until);}
    private final InputDispatcher input;
    PortableSkillRuntime(PortableSkillCodec.Package pkg,AccessibilityBindingResolver.RootSource source,BooleanSupplier cancelled){
        this(pkg,source,cancelled,(target,skill,value,until)->skill.equals("SetPower")
            ?AccessibilityBindingResolver.clickPrepared(target,until)
            :AccessibilityRangeExecutor.setPreparedProgress(target,((Integer)value).doubleValue(),until));
    }
    // Package-local boundary seam for controlled SDK-ack tests; not exposed by the App protocol.
    PortableSkillRuntime(PortableSkillCodec.Package pkg,AccessibilityBindingResolver.RootSource source,BooleanSupplier cancelled,InputDispatcher input){
        this.pkg=pkg;this.cancelled=cancelled;
        this.input=Objects.requireNonNull(input);
        this.source=()->{while(true){guard();try{var frame=source.read();guard();if(frame==null||frame.root==null)throw new IllegalStateException("NO_TREE");return frame;}
            catch(RuntimeException e){if(!PortableObservationPolicy.retryObservation(e.getMessage()))throw e;retryObservation(e.getMessage());}}};
    }
    private void guard(){if(cancelled.getAsBoolean())throw new IllegalStateException("CANCELLED");WorkflowTiming.requireBeforeDeadline(SystemClock.elapsedRealtime(),deadline);}
    private void retryObservation(String reason){
        guard();recovery.put(new JSONObject(Map.of("reason",reason,"ms",SystemClock.elapsedRealtime())));
        long wait=Math.min(80,deadline-SystemClock.elapsedRealtime());if(wait<=0)guard();SystemClock.sleep(wait);
    }
    private AccessibilityBindingResolver.Resolved resolve(String key)throws Exception {
        guard();long start=SystemClock.elapsedRealtime();
        try {while(true){try{var r=AccessibilityBindingResolver.resolveFresh(source,pkg.binding.targets.get(key),PortableSkillCodec.PAGE,-1);
            Rect b=new Rect();r.node.getBoundsInScreen(b);
            resolved.put(new JSONObject().put("property",key).put("id",r.node.getViewIdResourceName()).put("class",r.node.getClassName())
                .put("strategy",r.strategy).put("generation",r.generation).put("bounds",new JSONArray(new int[]{b.left,b.top,b.right,b.bottom})));
            return r;
        }catch(RuntimeException e){if(!PortableObservationPolicy.retryObservation(e.getMessage()))throw e;retryObservation(e.getMessage());}}
        }finally{resolveMs+=SystemClock.elapsedRealtime()-start;}
    }
    private Object value(String key,AccessibilityBindingResolver.Resolved r){
        if(key.endsWith(".power")){if(!r.node.isCheckable())throw new IllegalStateException("NOT_CHECKABLE");return r.node.isChecked()?"on":"off";}
        var range=r.node.getRangeInfo();if(range==null||!Float.isFinite(range.getCurrent())||range.getCurrent()!=Math.rint(range.getCurrent()))throw new IllegalStateException("INVALID_OBSERVATION");
        return (int)range.getCurrent();
    }
    private Map<String,Object> observe()throws Exception {return observe(null);}
    private Map<String,Object> observe(String target)throws Exception {
        guard();long started=SystemClock.elapsedRealtime();
        try{
            while(true){try{var frame=source.read();if(frame==null||frame.root==null)throw new IllegalStateException("NO_TREE");
            Map<String,Object> state=new LinkedHashMap<>();
            for(String key:target==null?new TreeSet<>(pkg.binding.targets.keySet()):Collections.singleton(target)){
                var r=AccessibilityBindingResolver.resolve(key,pkg.binding,frame.root,frame.page);
                if(r.status!=EnvironmentBinding.Status.RESOLVED)throw new IllegalStateException(r.reason);
                state.put(key,value(key,r.resolved));
            }
            guard();last=Map.copyOf(state);lastComplete=target==null;
            observations.put(new JSONObject().put("ms",SystemClock.elapsedRealtime()).put("scope",lastComplete?"FULL":"TARGET_ONLY").put("state",new JSONObject(state)));return last;
            }catch(RuntimeException e){if(!PortableObservationPolicy.retryObservation(e.getMessage()))throw e;retryObservation(e.getMessage());}}
        }finally{verifyMs+=SystemClock.elapsedRealtime()-started;}
    }
    private void await(String key,Object wanted,long confirmationUntil,boolean fullScope)throws Exception {
        while(true){Map<String,Object> state=observe(fullScope?null:key);
            WorkflowTiming.requireConfirmation(SystemClock.elapsedRealtime(),confirmationUntil,deadline);
            if(Objects.equals(state.get(key),wanted))return;
            guard();long wait=Math.min(80,deadline-SystemClock.elapsedRealtime());if(wait<=0)guard();SystemClock.sleep(wait);verifyMs+=wait;
        }
    }
    JSONObject run(JSONArray raw,int budgetMs)throws Exception {
        long started=SystemClock.elapsedRealtime();deadline=started+budgetMs;String status="REJECTED",reason="",stage="validation";
        long validationNs=0;boolean validationAttempted=false,validationSucceeded=false;
        SemanticSkills.Plan plan=null;
        try{
            if(budgetMs<1||budgetMs>10000)throw new IllegalArgumentException("BUDGET");
            long validationStarted=SystemClock.elapsedRealtimeNanos();validationAttempted=true;
            try{plan=pkg.compile(raw);validationSucceeded=true;}
            finally{validationNs=SystemClock.elapsedRealtimeNanos()-validationStarted;}
            stage="resolution";guard();initial=observe();
            boolean noop=SemanticSkills.allCallsSatisfied(plan.calls,initial);
            Map<String,Object> expectedAfter=new LinkedHashMap<>(initial);
            for(var call:plan.calls){
                stage="resolution";guard();var r=resolve(call.propertyKey());
                if(Objects.equals(value(call.propertyKey(),r),call.value))continue;
                // Authorize against a fresh whole context before recording an Android input.
                long preparing=SystemClock.elapsedRealtime();
                var prepared=AccessibilityBindingResolver.forAction(source,r);
                if(call.skill.equals("SetPower")){if(!prepared.node.isClickable())throw new IllegalStateException("NOT_CLICKABLE");}
                else AccessibilityRangeExecutor.plan(prepared.node,((Integer)call.value).doubleValue(),null);
                resolveMs+=SystemClock.elapsedRealtime()-preparing;
                stage="execution";guard();long began=SystemClock.elapsedRealtime();boolean accepted;
                String method=call.skill.equals("SetPower")?"CLICK":"SET_PROGRESS";
                JSONObject action=new JSONObject().put("property",call.propertyKey()).put("value",call.value).put("method",method).put("ms",began).put("accepted",false);
                actions.put(action); // A fresh one-use permit exists; rejected Binder calls stay recorded.
                lastComplete=false; // Input may have taken effect even when its SDK acknowledgement is lost.
                action.put("effect_verified",false).put("ack_status","NOT_RETURNED");
                try {
                    accepted=input.dispatch(prepared,call.skill,call.value,deadline);
                } finally {inputMs+=SystemClock.elapsedRealtime()-began;}
                action.put("accepted",accepted).put("sdk_acknowledged",accepted).put("ack_status","RETURNED");
                // Never resend an uncertain toggle. Observe inside the same task/cancellation budget.
                stage="verification";
                try {await(call.propertyKey(),call.value,accepted?deadline:WorkflowTiming.confirmationDeadline(SystemClock.elapsedRealtime(),deadline),!accepted);}
                catch(IllegalStateException uncertain){
                    if(accepted||!"STEP_UNCONFIRMED".equals(uncertain.getMessage()))throw uncertain;
                    // Reuse the current complete negative observation; a redundant read
                    // here can exhaust the remaining launch/task budget.
                    guard();if(!lastComplete)throw new IllegalStateException("INCOMPLETE_EFFECT_OBSERVATION");stage="execution";
                    throw new IllegalStateException("INPUT_REJECTED"); // FAILED means task not completed, not proof of no effect.
                }
                expectedAfter.put(call.propertyKey(),call.value);
                if(!accepted){
                    if(!lastComplete||!last.equals(expectedAfter))throw new IllegalStateException("UNCERTAIN_INPUT_STATE_MISMATCH");
                }
                action.put("effect_verified",true).put("effect_observation_ms",SystemClock.elapsedRealtime())
                    .put("effect_observation_complete",lastComplete).put("effect_observed_state",new JSONObject(last));
            }
            stage="verification";Map<String,Object> finalState=observe();
            for(var goal:plan.goals.entrySet())if(!Objects.equals(finalState.get(goal.getKey()),goal.getValue()))throw new IllegalStateException("FINAL_GOAL_MISMATCH");
            for(var row:initial.entrySet())if(!plan.goals.containsKey(row.getKey())&&!Objects.equals(finalState.get(row.getKey()),row.getValue()))throw new IllegalStateException("UNMENTIONED_FIELD_CHANGED");
            guard();status=noop&&actions.length()==0?"NO_ACTION_REQUIRED":"SUCCESS";
        }catch(Exception e){
            reason=e.getMessage()==null?e.getClass().getSimpleName():e.getMessage();
            if(SystemClock.elapsedRealtime()>=deadline&&!Set.of("NO_TREE","ROOT_READ_FAILED","SERVICE_UNAVAILABLE").contains(reason))reason="DEADLINE / "+reason;
            status=PortableObservationPolicy.failureStatus(stage,reason);
        }
        return new JSONObject().put("run_id",UUID.randomUUID().toString()).put("package_hash",pkg.hash).put("registry_hash",SemanticSkills.registryHash())
            .put("validation_attempted",validationAttempted).put("validation_succeeded",validationSucceeded)
            .put("calls",raw).put("initial_state",new JSONObject(initial)).put("resolved_element",resolved).put("execution_actions",actions)
            .put("observations",observations).put("observation_recovery",recovery).put("final_observed_state",new JSONObject(last)).put("final_observation_complete",lastComplete).put("verification_result",status.equals("SUCCESS")||status.equals("NO_ACTION_REQUIRED"))
            .put("final_status",status).put("failure_stage",stage).put("reason",reason).put("latency",new JSONObject().put("runtime_ms",SystemClock.elapsedRealtime()-started)
                .put("validation_ns",validationNs).put("validation_ms",validationNs/1000000.0).put("validation_source","RUNTIME_COMPILE_ELAPSED_REALTIME_NANOS")
                .put("resolve_ms",resolveMs).put("execution_ms",inputMs).put("verification_ms",verifyMs));
    }
}
