package edu.sydney.probe;
import android.content.*;
import android.os.*;
import org.json.*;
import java.util.UUID;

/** User-declared read-only demonstration collection. No business input or node persistence. */
final class UserLearningSession {
    private static final Handler handler=new Handler(Looper.getMainLooper());
    private static JSONObject session;private static boolean active,scopeStarted;private static Context context;
    private static final Runnable tick=UserLearningSession::capture;
    static boolean active(){return active;}
    static void start(Context c,String pkg,String goal)throws Exception{
        if(active)throw new IllegalStateException("LEARNING_BUSY");
        var service=ProbeService.current();
        if(service==null||service.getServiceInfo()==null)throw new IllegalStateException("SERVICE_NOT_BOUND");
        if(service.workflowRunning()||service.workflowPreparing()||service.isRecording())throw new IllegalStateException("SERVICE_BUSY");
        if(!LearningScope.allowedPackage(pkg))throw new IllegalStateException("APP_NOT_IN_LEARNING_SCOPE");
        SemanticParameterCodec.text(goal,2000);
        String id=UUID.randomUUID().toString().replace("-","");context=c.getApplicationContext();
        // The launch itself can produce Probe/launcher window events. Arm the
        // existing collection scope ONLY after a fresh Root belongs to the
        // explicitly selected App; do not weaken LearningCapture's scope guard.
        scopeStarted=false;
        session=new JSONObject().put("id",id).put("goal",goal).put("app_package",pkg)
            .put("started_elapsed_ms",SystemClock.elapsedRealtime()).put("observations",new JSONArray())
            .put("actor","HUMAN_DECLARED_NOT_INDEPENDENTLY_ATTRIBUTED").put("state","RECORDING")
            .put("execution_authority",false).put("business_input_calls",0).put("model_calls",0)
            .put("last_capture_error",JSONObject.NULL);
        active=true;try{save();handler.postDelayed(tick,900);}catch(Exception e){active=false;throw e;}
    }
    private static void capture(){
        if(!active)return;
        try{
            var service=ProbeService.current();
            if(service==null||service.getServiceInfo()==null)throw new IllegalStateException("SERVICE_NOT_BOUND");
            android.view.accessibility.AccessibilityNodeInfo root=service.getRootInActiveWindow();
            String pkg="";try{if(root!=null&&root.getPackageName()!=null)pkg=root.getPackageName().toString();}finally{if(root!=null)root.recycle();}
            long now=SystemClock.elapsedRealtime();
            String decision=UserLearningCaptureGate.decide(session.getLong("started_elapsed_ms"),now,scopeStarted,session.getString("app_package"),pkg);
            if(decision.equals("WAIT_FOR_APP")){handler.postDelayed(tick,250);return;}
            if(decision.startsWith("STOP_"))throw new IllegalStateException(decision);
            if(decision.equals("ARM_AND_CAPTURE")){
                LearningCapture.start(session.getString("id"),pkg,now);scopeStarted=true;
                session.put("scope_started_elapsed_ms",now);
            }
            LearningCapture.require(session.getString("id"));
            var observation=LearningCapture.capture(service,session.getString("id"),UUID.randomUUID().toString().replace("-",""));
            var observations=session.getJSONArray("observations");observations.put(observation);
            if(session.toString().getBytes(java.nio.charset.StandardCharsets.UTF_8).length>786432){
                observations.remove(observations.length()-1);throw new IllegalStateException("LEARNING_STORAGE_LIMIT");
            }
            session.put("last_capture_error",JSONObject.NULL);save();
            handler.postDelayed(tick,900);
        }catch(Exception error){
            try{session.put("last_capture_error",String.valueOf(error.getMessage()));finish(false);}catch(Exception ignored){active=false;handler.removeCallbacks(tick);}
        }
    }
    static JSONObject finish(boolean cancelled)throws Exception{
        if(session==null)throw new IllegalStateException("NO_LEARNING_SESSION");
        if(!active&&session.has("finished_elapsed_ms"))return new JSONObject(session.toString());
        active=false;handler.removeCallbacks(tick);
        Object events=scopeStarted?LearningCapture.cancel(session.getString("id")):
            new JSONObject().put("events",new JSONArray()).put("events_truncated",false).put("sequence",0);
        scopeStarted=false;
        session.put("events",events)
            .put("state",cancelled?"CANCELLED":session.isNull("last_capture_error")?"STOPPED":"INCOMPLETE")
            .put("finished_elapsed_ms",SystemClock.elapsedRealtime());save();return new JSONObject(session.toString());
    }
    static JSONObject read(Context c)throws Exception{
        try(var in=c.openFileInput("c2-recording.json")){
            var out=new JSONObject(UserLearningFiles.read(in,1048576));
            if(!active&&"RECORDING".equals(out.optString("state")))out.put("state","INTERRUPTED").put("last_capture_error","PROCESS_RESTARTED_NO_RESUME_AUTHORITY");
            return out;
        }
    }
    private static void save()throws Exception{
        byte[] bytes=session.toString().getBytes(java.nio.charset.StandardCharsets.UTF_8);
        if(bytes.length>1048576)throw new IllegalStateException("LEARNING_STORAGE_LIMIT");
        var file=new android.util.AtomicFile(new java.io.File(context.getFilesDir(),"c2-recording.json"));java.io.FileOutputStream out=null;
        try{out=file.startWrite();out.write(bytes);file.finishWrite(out);}catch(Exception e){if(out!=null)file.failWrite(out);active=false;handler.removeCallbacks(tick);throw e;}
    }
}
