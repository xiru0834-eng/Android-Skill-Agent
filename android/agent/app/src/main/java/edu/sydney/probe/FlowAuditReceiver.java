package edu.sydney.probe;
import android.content.*;
import org.json.*;
import java.io.*;
import java.util.*;

/** DUMP-restricted lab driver. Not a model tool; does not publish or grant enduring authority. */
public final class FlowAuditReceiver extends BroadcastReceiver {
    private static final Set<String> ids=new HashSet<>();
    @Override public void onReceive(Context context,Intent intent){
        if(!"edu.sydney.probe.FLOW_AUDIT".equals(intent.getAction()))return;
        String id=intent.getStringExtra("request_id");if(id==null||!id.matches("[0-9a-f]{32}"))return;
        var pending=goAsync();
        try{
            if(!ids.add(id)||new File(context.getFilesDir(),"flow-audit-"+id+".json").exists())throw new IllegalStateException("DUPLICATE_REQUEST");
            var service=ProbeService.current();
            if("status".equals(intent.getStringExtra("operation"))){write(context,id,ProbeService.connectionAudit().put("final_status",service==null?"SERVICE_OFF":"READY").put("busy",service!=null&&service.workflowRunning()).put("process_session",LearningCapture.PROCESS_SESSION).put("unfinished_workers",service==null?JSONObject.NULL:service.unfinishedPortableWorkers()).put("window_metadata",service==null?JSONObject.NULL:service.admissionWindowMetadata()));pending.finish();return;}
            if(service==null)throw new IllegalStateException("SERVICE_OFF");
            if("cancel".equals(intent.getStringExtra("operation"))){service.stopAll();write(context,id,new JSONObject().put("final_status","CANCELLED"));pending.finish();return;}
            if(!"execute".equals(intent.getStringExtra("operation"))||!intent.getBooleanExtra("confirmed",false))throw new IllegalStateException("VALIDATION_AUTHORITY_REQUIRED");
            String raw;try(var in=context.openFileInput("flow-incoming.json")){raw=SkillFiles.read(in,131072);}
            if(!PortableSkillCodec.hash(raw).equals(intent.getStringExtra("plan_raw_hash")))throw new IllegalStateException("PLAN_CHANGED");
            Set<String> writes=new TreeSet<>();String allowed=intent.getStringExtra("allowed_writes");
            if(allowed==null)throw new IllegalStateException("VALIDATION_AUTHORITY_REQUIRED");
            if(!allowed.isEmpty())for(String key:allowed.split(",",-1)){if(!key.matches("[a-z][a-z0-9_]{0,63}\\.[A-Za-z][A-Za-z0-9]{0,63}")||!writes.add(key))throw new IllegalStateException("WRITE_POLICY");}
            String mode=intent.getStringExtra("mode");if(!Set.of("TEST_FIXTURE","CANDIDATE_VALIDATION").contains(mode))throw new IllegalStateException("FLOW_MODE");
            // Admission and task completion are different lifetimes. Holding goAsync
            // until runtime completion serializes a later cancel broadcast behind it.
            service.runFlow(new JSONObject(raw),writes,mode,result->write(context,id,result));
            pending.finish();
        }catch(Exception e){try{write(context,id,new JSONObject().put("final_status","REJECTED").put("reason",e.getMessage()).put("execution_actions",new JSONArray()).put("verification_result",false));}catch(Exception ignored){}pending.finish();}
    }
    private static void write(Context context,String id,JSONObject result){
        try{
            result.put("request_id",id).put("transport_channel","DUMP_RESTRICTED_LAB_EVALUATOR");
            var file=new android.util.AtomicFile(new File(context.getFilesDir(),"flow-audit-"+id+".json"));FileOutputStream out=null;
            try{out=file.startWrite();out.write(result.toString().getBytes(java.nio.charset.StandardCharsets.UTF_8));file.finishWrite(out);}
            catch(Exception e){if(out!=null)file.failWrite(out);throw e;}
        }catch(Exception error){android.util.Log.e("DemoProbe","Flow receipt storage failed");}
    }
}
