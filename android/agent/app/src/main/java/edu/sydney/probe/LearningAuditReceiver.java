package edu.sydney.probe;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.os.SystemClock;
import android.util.AtomicFile;
import java.io.File;
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashSet;
import org.json.*;

/** Caller must hold DUMP. Disabled until explicit scoped START; no model/network/skill execution. */
public final class LearningAuditReceiver extends BroadcastReceiver {
    private static final LinkedHashSet<String> ids=new LinkedHashSet<>();
    @Override public void onReceive(Context context,Intent intent){
        if(intent==null||!"edu.sydney.probe.LEARNING_AUDIT".equals(intent.getAction()))return;
        String id=intent.getStringExtra("request_id");if(!LearningScope.validId(id))return;
        JSONObject receipt=new JSONObject();
        try{
            receipt.put("request_id",id).put("schema_version","1.0").put("channel","REAL_ANDROID_BOUND_SERVICE")
                .put("process_session",LearningCapture.PROCESS_SESSION).put("received_elapsed_ms",SystemClock.elapsedRealtime())
                .put("input_api_calls",0).put("paid_requests",0).put("skill_runs",0);
            if(ids.contains(id))throw new IllegalStateException("DUPLICATE_REQUEST");
            if(ids.size()>=512)throw new IllegalStateException("REQUEST_BUDGET_EXCEEDED");ids.add(id);
            String op=intent.getStringExtra("operation"),scope=intent.getStringExtra("scope_id");receipt.put("operation",op);
            var service=ProbeService.current();if(service==null)throw new IllegalStateException("SERVICE_UNAVAILABLE");
            if(service.workflowRunning()||service.workflowPreparing()||service.isRecording())throw new IllegalStateException("SERVICE_BUSY");
            switch(op==null?"":op){
                case "start":LearningCapture.start(scope,intent.getStringExtra("app_package"),SystemClock.elapsedRealtime());receipt.put("status","STARTED");break;
                case "capture":receipt.put("observation",LearningCapture.capture(service,scope,id)).put("status","COLLECTED");break;
                case "click":
                    JSONObject dispatch=LearningCapture.click(service,scope,intent.getStringExtra("observation_id"),intent.getStringExtra("node_local_id"));
                    receipt.put("dispatch",dispatch).put("input_api_calls",dispatch.getInt("input_api_calls")).put("status",dispatch.getBoolean("dispatched")?"DISPATCHED":"EXECUTION_ERROR");break;
                case "events":LearningCapture.require(scope);receipt.put("event_record",LearningCapture.eventCopy()).put("status","EVENTS");break;
                case "stop":receipt.put("event_record",LearningCapture.finish(scope)).put("status","STOPPED");break;
                case "cancel":receipt.put("event_record",LearningCapture.cancel(scope)).put("status","CANCELLED");break;
                default:throw new IllegalStateException("UNKNOWN_OPERATION");
            }
        }catch(Exception e){try{receipt.put("status","REJECTED").put("error",e.getMessage()==null?e.getClass().getSimpleName():e.getMessage());
            JSONArray frames=new JSONArray();for(var frame:e.getStackTrace()){if(frames.length()>=8)break;frames.put(frame.getClassName()+"."+frame.getMethodName()+":"+frame.getLineNumber());}
            receipt.put("diagnostic_frames",frames);
            if("capture".equals(intent.getStringExtra("operation")))receipt.put("capture_failure",LearningCapture.failure());}catch(JSONException ignored){}}
        try{receipt.put("counters",LearningCapture.counters());}catch(JSONException ignored){}
        AtomicFile file=new AtomicFile(new File(context.getFilesDir(),"learning-audit.json"));FileOutputStream out=null;
        try{byte[] bytes=receipt.toString().getBytes(StandardCharsets.UTF_8);if(bytes.length>2*1024*1024)throw new IllegalStateException("RECEIPT_SIZE_LIMIT");
            out=file.startWrite();out.write(bytes);file.finishWrite(out);}
        catch(Exception error){if(out!=null)file.failWrite(out);android.util.Log.e("DemoProbe","Learning audit storage failed",error);}
    }
}
