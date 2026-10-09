package edu.sydney.probe;

import android.content.Context;
import android.os.SystemClock;
import android.view.accessibility.AccessibilityNodeInfo;
import org.json.JSONArray;
import org.json.JSONObject;
import java.util.TreeSet;

/** Thin package-local port, not an exported Android component or transport.
 * Host must supply its ORIGINAL guarded RootSource (window/launch/overlay checks).
 * The P1.3 caller retains Flow READ/ASSERT/order checks; each CALL uses old Runtime.
 * ProbeService invokes this port through the whole-Flow coordinator; no SDK
 * action is implemented here outside the original guarded runtime.
 */
final class FlowLegacyPort implements AutoCloseable {
    static final boolean DEFAULT_ENABLED=false;
    private final Context context;
    private final FlowTaskGate gate;
    private final AccessibilityBindingResolver.RootSource source;
    private final PortableSkillCodec.Package pkg;
    private long sequence;
    private final FlowTiming timing;
    private final FlowReviewSnapshot approval;
    private final ResolverTimingProbe.Scope resolverScope;

    private static void need(boolean valid,String reason){if(!valid)throw new IllegalStateException(reason);}
    static FlowLegacyPort open(boolean enabled,Context context,
                               AccessibilityBindingResolver.RootSource originalGuardedSource,FlowTaskGate gate,FlowTiming timing)throws Exception {
        need(enabled,"FEATURE_DISABLED"); // Do not read approval/store/Root while disabled.
        need(context!=null&&originalGuardedSource!=null&&gate!=null,"HOST_INTEGRATION_REQUIRED");
        var pkg=new PortableSkillStore(context).approved(); // Original Codec, version and local raw-hash approval.
        need(pkg.hash.equals(gate.rawPackageHash),"RAW_APPROVAL_MISMATCH");
        gate.claim(gate.planHash,pkg.hash,gate.environmentHash,SystemClock.elapsedRealtime());
        return new FlowLegacyPort(context,originalGuardedSource,gate,pkg,timing);
    }
    private FlowLegacyPort(Context context,AccessibilityBindingResolver.RootSource hostSource,
                           FlowTaskGate gate,PortableSkillCodec.Package pkg,FlowTiming timing){
        this.context=context;this.gate=gate;this.pkg=pkg;this.timing=timing;
        approval=new FlowReviewSnapshot(pkg.raw,pkg.hash,pkg.appVersion);
        source=()->{
            guard();currentApproval();
            AccessibilityBindingResolver.Frame frame;
            try(var span=timing.span("guard.current_root")){frame=hostSource.read();} // Original window guard.
            try{
                guard();need(frame!=null&&frame.root!=null,"NO_TREE");
                need(PortableSkillCodec.PAGE.equals(frame.page),"PAGE_CHANGED");
                need(PortableSkillCodec.PKG.contentEquals(frame.root.getPackageName()==null?"":frame.root.getPackageName()),"BLOCKED_BY_OVERLAY");
                return frame;
            }catch(RuntimeException error){if(frame!=null&&frame.root!=null)frame.root.recycle();throw error;}
        };
        resolverScope=timing.openResolverScope();
    }
    private void guard(){gate.guard(gate.planHash,pkg.hash,gate.environmentHash,SystemClock.elapsedRealtime());}
    private void currentApproval(){
        try(var span=timing.span("guard.legacy_current_bytes")){
            String raw;try(var input=context.openFileInput("portable-approved.json")){raw=SkillFiles.read(input,24000);}
            approval.check(raw,context.getSharedPreferences("portable_approval",0).getString("hash",""),
                context.getPackageManager().getPackageInfo(PortableSkillCodec.PKG,0).versionName);
        }
        catch(RuntimeException error){throw error;}
        catch(Exception error){throw new IllegalStateException("LEGACY_APPROVAL_UNAVAILABLE");}
    }
    JSONObject observe(String phase)throws Exception {
        return observe(phase,pkg.binding.targets.keySet());
    }
    JSONObject observe(String phase,java.util.Set<String> properties)throws Exception {
        need(phase!=null&&phase.matches("[a-zA-Z0-9_.:-]{1,80}"),"OBSERVATION_PHASE_ERROR");
        need(properties!=null&&pkg.binding.targets.keySet().containsAll(properties),"READ_CONTRACT_MISMATCH");
        guard();var frame=source.read();JSONObject state=new JSONObject();JSONArray validationCalls=new JSONArray();
        try{
            for(String key:new TreeSet<>(properties)){
                AccessibilityBindingResolver.Result result;
                try(var span=timing.span("resolve."+key)){result=AccessibilityBindingResolver.resolve(key,pkg.binding,frame.root,frame.page);}
                need(result.status==EnvironmentBinding.Status.RESOLVED,result.reason);
                var node=result.resolved.node;
                try{
                    Object value;
                    if(key.endsWith(".power")){need(node.isCheckable(),"NOT_CHECKABLE");value=node.isChecked()?"on":"off";}
                    else{
                        var range=node.getRangeInfo();need(range!=null&&Float.isFinite(range.getCurrent())&&range.getCurrent()==Math.rint(range.getCurrent()),"INVALID_OBSERVATION");
                        value=(int)range.getCurrent();
                    }
                    state.put(key,value);
                    for(var entity:pkg.semantics.entities.entities)for(String skill:entity.capabilities){
                        var definition=SemanticSkills.definition(skill);
                        if(key.equals(entity.id+"."+definition.property))validationCalls.put(new JSONObject().put("skill",skill)
                            .put("args",new JSONObject().put("device",entity.id).put(definition.argument,value)));
                    }
                }finally{if(node!=frame.root)node.recycle();}
            }
            if(validationCalls.length()>0)pkg.compile(validationCalls); // Preserve original entity domains for observed values too.
            guard();return new JSONObject().put("kind","semantic_state_read_v1").put("channel","ANDROID_NATIVE")
                .put("task_id",gate.taskId).put("host_device_id",gate.hostDeviceId).put("environment_hash",gate.environmentHash)
                .put("observation_session_id",gate.sessionId).put("phase",phase).put("sequence",++sequence)
                .put("captured_elapsed_ms",SystemClock.elapsedRealtime()).put("values",state)
                .put("complete",properties.equals(pkg.binding.targets.keySet())).put("observed_properties",new JSONArray(new TreeSet<>(properties)));
        }finally{frame.root.recycle();}
    }
    JSONObject runOne(JSONArray oneCall)throws Exception {
        guard();currentApproval();need(oneCall!=null&&oneCall.length()==1,"SINGLE_CALL_REQUIRED");
        var call=pkg.compile(oneCall).calls.get(0); // Original wire/type/entity/domain checks.
        gate.authorizeCall(call.propertyKey(),gate.planHash,pkg.hash,gate.environmentHash,SystemClock.elapsedRealtime());
        int remaining=(int)Math.min(10000,gate.deadlineMs-SystemClock.elapsedRealtime());
        need(remaining>0,"TASK_DEADLINE_EXCEEDED");
        var runtime=new PortableSkillRuntime(pkg,source,()->{
            guard();return false; // Old runtime additionally keeps its own deadline guard.
        },(prepared,skill,value,until)->{
            guard(); // Original forAction already refreshed/consumed a one-shot permit.
            long deadline=Math.min(until,gate.deadlineMs);
            return skill.equals("SetPower")?AccessibilityBindingResolver.clickPrepared(prepared,deadline)
                :AccessibilityRangeExecutor.setPreparedProgress(prepared,((Integer)value).doubleValue(),deadline);
        });
        var receipt=runtime.run(oneCall,remaining);
        // An input can already have been issued when cancellation/deadline fires.
        // Preserve the executor receipt instead of throwing away its action audit.
        try{guard();}catch(RuntimeException stopped){
            receipt.put("verification_result",false).put("final_status",stopped.getMessage().equals("CANCELLED")?"CANCELLED":"UNCONFIRMED").put("reason",stopped.getMessage());
        }
        return receipt.put("flow_scope","SINGLE_LEGACY_CALL_NOT_WHOLE_FLOW").put("channel","ANDROID_NATIVE")
            .put("task_deadline_ms",gate.deadlineMs).put("flow_plan_hash",gate.planHash);
    }
    public void close(){try{gate.close();}finally{resolverScope.close();}}
}
