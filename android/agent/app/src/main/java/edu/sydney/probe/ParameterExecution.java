package edu.sydney.probe;
import android.content.Context;
import org.json.*;

/** One invocation authorization, created only after the local call-and-binding preview. */
final class ParameterExecution {
    final String plan,sourceId,sourceName;
    final long localPreflightMs;
    private final String sourceRaw,callsRaw,bindingSnapshot;
    private final WorkflowStore store;
    private final Context context;
    ParameterExecution(Context context,NamedWorkflowPolicy.Entry source,JSONArray calls)throws Exception{
        long began=android.os.SystemClock.elapsedRealtime();
        this.context=context;store=new WorkflowStore(context);sourceRaw=source.raw;sourceId=source.id;sourceName=source.name;callsRaw=new JSONArray(calls.toString()).toString();
        bindingSnapshot=ParameterBindingStore.localSnapshot(context,source);
        plan=ParameterSkillCodec.compile(sourceRaw,new JSONArray(callsRaw)).toString();
        if(!current())throw new IllegalArgumentException("PARAMETER_BINDING_CHANGED");
        localPreflightMs=android.os.SystemClock.elapsedRealtime()-began;
    }
    boolean current(){
        try{var entry=store.find(sourceId);return !store.storageUnconfirmed()&&entry!=null&&entry.raw.equals(sourceRaw)&&entry.name.equals(sourceName)&&store.sameVersion(sourceRaw)&&bindingSnapshot.equals(ParameterBindingStore.localSnapshot(context,entry));}
        catch(Exception error){return false;}
    }
    boolean noActionRequired(int[] saved)throws Exception{
        java.util.List<SemanticSkills.Call> calls=new java.util.ArrayList<>();
        for(var call:ParameterSkillCodec.calls(new JSONArray(callsRaw)))calls.add(new SemanticSkills.Call(call.skill,call.device,call.value));
        return SemanticSkills.allCallsSatisfied(calls,TransferLabParameterAdapter.observedValues(saved));
    }
    JSONObject audit()throws Exception{
        return new JSONObject().put("kind","PARAMETERIZED_RUN").put("sourceSkillId",sourceId).put("sourceSkillName",sourceName)
            .put("calls",new JSONArray(callsRaw)).put("binding",new JSONObject().put("appPackage",WorkflowUi.PKG)
                .put("appVersion",WorkflowCodec.decode(sourceRaw).getString("appVersion")).put("startPage",ParameterSkillCodec.binding(sourceRaw).startPage))
            .put("planOrigin","LOCAL_COMPILER_NOT_RECORDED_TRACE").put("coordinateReplay",false)
            .put("bindingSource","LOCAL_REVIEWED_SOURCE").put("requiresPackageFile",false);
    }
}
