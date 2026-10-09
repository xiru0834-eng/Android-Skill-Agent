package edu.sydney.probe;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.graphics.Rect;
import android.util.AtomicFile;
import android.view.accessibility.AccessibilityNodeInfo;
import android.view.accessibility.AccessibilityWindowInfo;
import java.io.File;
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.TreeSet;
import org.json.*;

/** DUMP-protected, explicit read-only audit of the actual bound production service. */
public final class PrerequisiteAuditReceiver extends BroadcastReceiver {
    @Override public void onReceive(Context context,Intent intent){
        String id=intent==null?null:intent.getStringExtra("request_id");
        if(intent==null||!PrerequisiteAuditPolicy.accepts(intent.getAction(),id))return;
        JSONObject receipt=new JSONObject();
        try{
            receipt.put("request_id",id).put("capturedElapsedMs",android.os.SystemClock.elapsedRealtime())
                .put("collector","BOUND_PROBE_SERVICE_READ_ONLY").put("callerPackage",context.getPackageName())
                .put("processUid",android.os.Process.myUid()).put("inputAPICalls",0).put("skillRuns",0).put("paidRequests",0);
            var service=ProbeService.current();if(service==null)throw new IllegalStateException("SERVICE_UNAVAILABLE");
            if(service.workflowRunning()||service.workflowPreparing()||service.isRecording())throw new IllegalStateException("SERVICE_BUSY");
            var pkg=new PortableSkillStore(service).approved();
            receipt.put("registry",DeviceContextCodec.registryReceipt()).put("packageHash",pkg.hash).put("compiledCatalog",pkg.catalog);
            long deadline=android.os.SystemClock.elapsedRealtime()+ReadOnlyObservationRetry.TOTAL_BUDGET_MS;
            JSONArray attempts=new JSONArray();receipt.put("observationAttempts",attempts);
            for(int attempt=1;;attempt++){
                JSONObject entry=new JSONObject().put("attempt",attempt).put("startedElapsedMs",android.os.SystemClock.elapsedRealtime());
                attempts.put(entry);
                try{
                    JSONObject snapshot=capture(service,pkg,entry,deadline);
                    entry.put("status","COLLECTED").put("finishedElapsedMs",android.os.SystemClock.elapsedRealtime());
                    for(String key:new String[]{"rootReadable","rootPackage","page","deviceContext","keyNodes"})receipt.put(key,snapshot.get(key));
                    receipt.put("status","COLLECTED");break;
                }catch(Exception error){
                    long now=android.os.SystemClock.elapsedRealtime();
                    entry.put("status","FAILED").put("reason",error.getMessage()).put("finishedElapsedMs",now);
                    if(!ReadOnlyObservationRetry.retry(error.getMessage(),attempt,now,deadline))throw error;
                    android.os.SystemClock.sleep(ReadOnlyObservationRetry.delay(now,deadline));
                }
            }
        }catch(Exception error){try{receipt.put("status","FAILED").put("error",error.getClass().getSimpleName()+":"+error.getMessage());}catch(JSONException ignored){}}
        AtomicFile file=new AtomicFile(new File(context.getFilesDir(),"prerequisite-audit.json"));FileOutputStream out=null;
        try{out=file.startWrite();out.write(receipt.toString().getBytes(StandardCharsets.UTF_8));file.finishWrite(out);}
        catch(Exception error){if(out!=null)file.failWrite(out);android.util.Log.e("DemoProbe","Readonly audit storage failed",error);}
    }
    private static JSONObject capture(ProbeService service,PortableSkillCodec.Package pkg,JSONObject attempt,long deadline)throws Exception{
        AccessibilityNodeInfo root=null;List<AccessibilityWindowInfo> windows=null;
        try{
            ReadOnlyObservationRetry.requireCurrent(android.os.SystemClock.elapsedRealtime(),deadline);
            if(android.os.Build.VERSION.SDK_INT>=33)service.clearCache();
            root=service.getRootInActiveWindow();windows=service.getWindows();
            JSONArray metadata=new JSONArray();
            if(windows!=null)for(var w:windows)metadata.put(new JSONObject().put("id",w.getId()).put("type",w.getType()).put("layer",w.getLayer()).put("active",w.isActive()).put("focused",w.isFocused()));
            attempt.put("rootReadable",root!=null).put("windows",metadata);
            var frame=PortableWindowGuard.frame(root,windows);
            JSONObject snapshot=new JSONObject().put("rootReadable",true).put("rootPackage",root.getPackageName()).put("page",frame.page);
            snapshot.put("deviceContext",AndroidDeviceContext.capture(service,PortableSkillCodec.PKG));
            JSONArray nodes=new JSONArray();
            for(String key:new TreeSet<>(pkg.binding.targets.keySet())){
                var r=AccessibilityBindingResolver.resolve(key,pkg.binding,root,frame.page);
                JSONObject row=new JSONObject().put("property",key).put("resolutionStatus",r.status.name()).put("reason",r.reason);
                if(r.resolved!=null){try{row.put("node",node(r.resolved.node)).put("strategy",r.resolved.strategy).put("generation",r.resolved.generation);}finally{r.resolved.node.recycle();}}
                nodes.put(row);
            }
            ReadOnlyObservationRetry.requireCurrent(android.os.SystemClock.elapsedRealtime(),deadline);
            return snapshot.put("keyNodes",nodes);
        }finally{if(root!=null)root.recycle();if(windows!=null)for(var w:windows)w.recycle();}
    }
    private static JSONObject node(AccessibilityNodeInfo n)throws JSONException{
        Rect b=new Rect();n.getBoundsInScreen(b);var range=n.getRangeInfo();
        return new JSONObject().put("resource_id",n.getViewIdResourceName()).put("text",n.getText()==null?JSONObject.NULL:n.getText().toString())
            .put("contentDescription",n.getContentDescription()==null?JSONObject.NULL:n.getContentDescription().toString()).put("class",n.getClassName())
            .put("bounds",new JSONArray(new int[]{b.left,b.top,b.right,b.bottom})).put("clickable",n.isClickable()).put("selected",n.isSelected())
            .put("checkable",n.isCheckable()).put("checked",n.isChecked()).put("enabled",n.isEnabled()).put("visible",n.isVisibleToUser())
            .put("value",range==null?JSONObject.NULL:range.getCurrent()).put("range_min",range==null?JSONObject.NULL:range.getMin()).put("range_max",range==null?JSONObject.NULL:range.getMax());
    }
}
