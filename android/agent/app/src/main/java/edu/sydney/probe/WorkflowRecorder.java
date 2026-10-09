package edu.sydney.probe;

import android.os.*;
import android.view.accessibility.*;
import java.util.*;
import java.nio.charset.StandardCharsets;
import org.json.*;

/** Records observed click transitions. Unattributed changes invalidate compilation. */
final class WorkflowRecorder {
    private final ProbeService service;
    private final Handler handler=new Handler(Looper.getMainLooper());
    private JSONObject trace,last,pending,audit,layoutOrigin;
    private WorkflowRecordingPolicy settling;
    private String lastObservationError="";
    private final Runnable completion=this::complete;
    private Map<String,String> labels=new HashMap<>();
    private long started,changedSince;
    private long unknownForegroundSince=-1;
    private String lastForeground="";
    private boolean active;
    private WorkflowResources resources=WorkflowResources.defaults();
    private final Runnable tick=this::poll;
    WorkflowRecorder(ProbeService s){service=s;}
    boolean active(){return active;}
    int stepCount(){return trace==null?0:trace.optJSONArray("steps").length();}
    boolean ready(){return active&&last!=null;}
    String error(){return trace==null?"":trace.optString("error");}
    boolean inspectingLayout(){return layoutOrigin!=null;}
    boolean hasPending(){return pending!=null||changedSince!=0;}
    long elapsedMs(){return active?Math.max(0,SystemClock.elapsedRealtime()-started):0;}
    String traceId(){return trace==null?"":trace.optString("traceId");}
    String end(){return trace==null?"":trace.optString("end");}
    boolean automated(){return trace!=null&&"AUTOMATED".equals(trace.optString("source"));}
    boolean flexible(){return trace!=null&&trace.optInt("version")==2;}
    boolean savedOverview(){JSONObject state=trace==null?null:trace.optJSONObject("final");return state!=null&&List.of("overview","single").contains(state.optString("page"))&&!state.optBoolean("dirty",true);}
    boolean routeComplete(){if(trace!=null&&trace.optInt("version")==2){try{FlexibleWorkflowCodec.compile(trace.toString());return true;}catch(Exception e){return false;}}return TeachingRoute.complete(TeachingRecordView.ids(trace));}
    String nextAction(boolean en){return trace!=null&&trace.optInt("version")==2?(en?"Continue your workflow in any order. Save your changes before finishing.":"按你的流程继续操作，不限固定组合；保存修改后结束录制。"):TeachingRoute.next(TeachingRecordView.ids(trace),en);}
    String lastAction(boolean en){
        try {JSONArray steps=trace.getJSONArray("steps");if(steps.length()==0)return en?"Waiting for your first action":"等待你的第一个操作";
            JSONObject step=steps.getJSONObject(steps.length()-1);String id=step.getString("id");
            Boolean desired=(id.equals("wfLampPower")||id.equals("wfFanPower"))?step.getJSONObject("after").getJSONObject("values").getBoolean(id):null;
            return TeachingText.observed(id,desired,step.getJSONObject("after").getString("page"),en);
        }catch(Exception e){return en?"Action recorded":"操作已记录";}
    }
    void start(String goal,String source) {
        if(goal==null||goal.isBlank()||goal.length()>240||!List.of("AUTOMATED","HUMAN_DECLARED").contains(source))throw new IllegalArgumentException("GOAL_OR_SOURCE");
        stop("INTERRUPTED");
        try {
            resources=WorkflowResourceStore.read(service);
            String version=Long.toString(service.getPackageManager().getPackageInfo(WorkflowUi.PKG,0).getLongVersionCode());
            trace=new JSONObject().put("kind","WORKFLOW_TRACE").put("version",2).put("traceId",UUID.randomUUID().toString())
                .put("appPackage",WorkflowUi.PKG).put("appVersion",version).put("source",source).put("goal",goal)
                .put("end","RECORDING").put("error","").put("initial",JSONObject.NULL).put("steps",new JSONArray()).put("final",JSONObject.NULL);
            audit=new JSONObject().put("traceId",trace.getString("traceId")).put("events",new JSONArray());
            last=null;pending=null;layoutOrigin=null;lastObservationError="";started=SystemClock.elapsedRealtime();changedSince=0;unknownForegroundSince=-1;lastForeground="";active=true;save();handler.postDelayed(tick,100);
        }catch(Exception e){active=false;throw new IllegalStateException("RECORD_START_FAILED");}
    }
    void startPrepared(String goal,String source,String expected) {
        JSONObject now=WorkflowUi.recordingSnapshot(service);
        if(!now.toString().equals(expected)||now.optBoolean("dirty",true)||!List.of("overview","single").contains(now.optString("page")))throw new IllegalStateException("PREPARED_BASELINE_CHANGED");
        Map<String,String> currentLabels=WorkflowUi.labels(service);
        start(goal,source);
        try{last=now;labels=currentLabels;trace.put("initial",now).put("final",now);save();if(!active)throw new IllegalStateException("RECORD_STORAGE");}
        catch(JSONException e){fail("BASELINE_JSON");throw new IllegalStateException("BASELINE_JSON",e);}
    }
    void event(AccessibilityEvent event) {
        if(!active||event==null||!WorkflowUi.PKG.contentEquals(event.getPackageName())||event.getEventType()!=AccessibilityEvent.TYPE_VIEW_CLICKED)return;
        try {
            String foreground=foreground();
            if(!foreground.equals("APP")){fail(foreground.equals("OTHER")?"LEFT_ALLOWED_APPS":"FOREGROUND_UNCONFIRMED");return;}
            if(last==null){fail("CLICK_BEFORE_BASELINE");return;}
            AccessibilityNodeInfo source=event.getSource();String full=source==null?null:source.getViewIdResourceName();
            String id=full!=null&&full.startsWith(WorkflowUi.PKG+":id/")?full.substring((WorkflowUi.PKG+":id/").length()):null;
            String method="RESOURCE_ID";
            JSONArray candidates=null;
            if(id==null) {
                List<String> matches=new ArrayList<>();
                for(Map.Entry<String,String> entry:labels.entrySet())for(CharSequence t:event.getText())
                    if(!entry.getValue().isBlank()&&entry.getValue().contentEquals(t)&&!matches.contains(entry.getKey()))matches.add(entry.getKey());
                if(matches.size()>1&&flexible()){
                    candidates=new JSONArray(matches);method="UNIQUE_TRANSITION";
                }else if(matches.size()!=1){
                    JSONObject unresolved=new JSONObject().put("id",JSONObject.NULL).put("before",new JSONObject(last.toString()))
                        .put("eventTime",event.getEventTime()).put("attribution","UNRESOLVED").put("candidateIds",new JSONArray(matches));
                    audit.getJSONArray("events").put(new JSONObject(unresolved.toString()).put("kind","UNRESOLVED_CLICK"));
                    if(pending==null)pending=unresolved;
                    fail(layoutOrigin!=null?"SINGLE_PAGE_EDIT_NOT_SUPPORTED":"CLICK_SOURCE_UNRESOLVED");return;
                }else{id=matches.get(0);method="UNIQUE_LABEL";}
            }
            audit.getJSONArray("events").put(new JSONObject().put("kind","CLICK").put("id",id==null?JSONObject.NULL:id).put("eventTime",event.getEventTime()).put("attribution",method)
                .put("candidateIds",candidates==null?JSONObject.NULL:candidates));
            if(pending!=null){fail("OVERLAPPING_INPUT");return;}
            if(candidates==null&&!labels.containsKey(id)){fail("CLICK_NOT_IN_PREVIOUS_PAGE");return;}
            pending=new JSONObject().put("id",id==null?JSONObject.NULL:id).put("before",new JSONObject(last.toString())).put("eventTime",event.getEventTime()).put("attribution",method);
            if(candidates!=null)pending.put("candidateIds",candidates);
            if(layoutOrigin!=null&&!id.equals("wfMulti")){fail("SINGLE_PAGE_EDIT_NOT_SUPPORTED");return;}
            boolean noop=id!=null&&(WorkflowRecordingPolicy.safeNoop(id,last.getJSONObject("values").optBoolean(id,false),last.getString("page"))
                ||(trace.optInt("version")==2&&(id.endsWith("Save")||id.endsWith("Cancel")||id.equals("wfSingle")||id.equals("wfMulti"))));
            settling=new WorkflowRecordingPolicy(SystemClock.elapsedRealtime(),last.toString(),noop,flexible()?resources.confirmationMs():1500);
            lastObservationError="";changedSince=0;save();handler.postDelayed(completion,100);
        }catch(Exception e){fail("CLICK_EVIDENCE_ERROR");}
    }
    private void complete() {
        if(!active||pending==null)return;
        JSONObject after=null;long began=SystemClock.elapsedRealtime();
        try {
            String foreground=foreground();
            if(foreground.equals("OTHER")){fail("LEFT_ALLOWED_APPS");return;}
            if(foreground.equals("APP"))after=WorkflowUi.recordingSnapshot(service);
            else lastObservationError="FOREGROUND_UNCONFIRMED";
        }catch(Exception e){lastObservationError=e.getMessage();}
        long finished=SystemClock.elapsedRealtime();
        String decision=settling.observe(finished,after==null?null:after.toString());
        try{audit.getJSONArray("events").put(new JSONObject().put("kind","SETTLE_OBSERVATION").put("startedMs",began).put("finishedMs",finished).put("elapsedMs",finished-began)
            .put("decision",decision).put("observed",after==null?JSONObject.NULL:after).put("error",lastObservationError));}catch(JSONException ignored){}
        if(decision.equals("WAIT")){handler.postDelayed(completion,100);return;}
        if(decision.equals("TIMEOUT")){fail("OBSERVATION_TIMEOUT:"+(lastObservationError.isEmpty()?"NO_CONFIRMED_CHANGE":lastObservationError));return;}
        try {
            Map<String,String> nextLabels=WorkflowUi.labels(service);
            if(pending.isNull("id")){
                FlexibleWorkflow.State before=FlexibleWorkflowCodec.traceState(trace);
                if(!FlexibleWorkflowCodec.matches(pending.getJSONObject("before"),before)){fail("DISCONTINUOUS_ATTRIBUTION");return;}
                String resolved=FlexibleWorkflowCodec.resolve(before,pending.getJSONArray("candidateIds"),after);
                if(resolved.isEmpty()){fail("CLICK_TRANSITION_AMBIGUOUS");return;}pending.put("id",resolved);
            }
            String id=pending.getString("id");
            if(trace.optInt("version")==2){
                pending.put("after",after);trace.getJSONArray("steps").put(pending);trace.put("final",after);
            }else if(id.equals("wfSingle")&&last.getString("page").equals("overview")&&!last.getBoolean("dirty")&&after.getString("page").equals("single")
                &&last.getJSONArray("saved").toString().equals(after.getJSONArray("saved").toString())) {
                layoutOrigin=new JSONObject(last.toString());decision="LAYOUT_INSPECTION";
            }else if(layoutOrigin!=null) {
                if(!id.equals("wfMulti")||!layoutOrigin.toString().equals(after.toString())){fail("LAYOUT_RETURN_MISMATCH");return;}
                layoutOrigin=null;decision="LAYOUT_RETURN_UNCHANGED";
            }else if(!decision.equals("NOOP")) {
                if(after.getString("page").equals("single")){fail("UNSUPPORTED_LAYOUT_CHANGE");return;}
                pending.put("after",after);trace.getJSONArray("steps").put(pending);trace.put("final",after);
            }
            audit.getJSONArray("events").put(new JSONObject().put("kind",decision).put("step",new JSONObject(pending.toString())).put("observed",after));
            pending=null;last=after;labels=nextLabels;save();
        }catch(Exception e){fail("POST_OBSERVATION_FAILED:"+e.getMessage());}
    }
    private void poll() {
        if(!active)return;
        if(SystemClock.elapsedRealtime()-started>resources.recordingMs()){stop("TIMED_OUT");return;}
        try {
            String foreground=foreground();
            if(foreground.equals("OTHER")){fail("LEFT_ALLOWED_APPS");return;}
            if(foreground.equals("UNKNOWN")){
                long now=SystemClock.elapsedRealtime();if(unknownForegroundSince<0)unknownForegroundSince=now;
                if(WorkflowForegroundPolicy.expired(unknownForegroundSince,now)){fail("FOREGROUND_UNCONFIRMED");return;}
                handler.postDelayed(tick,100);return;
            }
            unknownForegroundSince=-1;
            if(foreground.equals("CONTROLLER")){handler.postDelayed(tick,100);return;}
            AccessibilityNodeInfo root=service.getRootInActiveWindow();String pkg=root==null||root.getPackageName()==null?"":root.getPackageName().toString();
            if(WorkflowUi.PKG.equals(pkg)&&pending==null) {
                JSONObject now=WorkflowUi.recordingSnapshot(service);
                if(last==null) {
                    if(!List.of("overview","single").contains(now.getString("page"))||now.getBoolean("dirty")){fail("START_NOT_OVERVIEW");return;}
                    last=now;labels=WorkflowUi.labels(service);trace.put("initial",now).put("final",now);save();
                }else if(!now.toString().equals(last.toString())) {
                    if(changedSince==0)changedSince=SystemClock.elapsedRealtime();
                    else if(SystemClock.elapsedRealtime()-changedSince>700){fail("UNATTRIBUTED_CHANGE");return;}
                }else changedSince=0;
            }else if(!pkg.isEmpty()&&!pkg.equals(service.getPackageName())&&!pkg.equals(WorkflowUi.PKG)){fail("LEFT_ALLOWED_APPS");return;}
        }catch(Exception unavailable){
            // Preserve the first changed diagnostic, without accepting partial state.
            String reason=String.valueOf(unavailable.getMessage());
            if(!reason.equals(lastObservationError)){
                lastObservationError=reason;
                android.util.Log.w("DemoProbe","Workflow observation unavailable: "+reason);
            }
        }
        if(active)handler.postDelayed(tick,100);
    }
    private String foreground()throws JSONException{
        String state=WorkflowForeground.read(service);
        if(!state.equals(lastForeground)){
            lastForeground=state;audit.getJSONArray("events").put(new JSONObject().put("kind","FOREGROUND").put("state",state).put("ms",SystemClock.elapsedRealtime()));save();
        }
        return state;
    }
    void stop(String end) {
        if(!active)return;
        try {if(trace.optString("error").isEmpty()&&(pending!=null||changedSince!=0||last==null||layoutOrigin!=null))trace.put("error","INCOMPLETE_STOP");
            audit.put("pending",pending==null?JSONObject.NULL:new JSONObject(pending.toString())).put("lastObservationError",lastObservationError);
            trace.put("end",end);}
        catch(JSONException ignored){}active=false;pending=null;handler.removeCallbacksAndMessages(null);save();
    }
    private void fail(String reason){try{trace.put("error",reason);}catch(Exception ignored){}stop("REJECTED");}
    private void save() {
        try {
            byte[] bytes=trace.toString().getBytes(StandardCharsets.UTF_8);
            if(bytes.length>262144)throw new IllegalStateException();
            audit.put("end",trace.getString("end")).put("error",trace.getString("error"));
            writeAtomic("workflow-audit-"+trace.getString("traceId")+".json",audit.toString().getBytes(StandardCharsets.UTF_8));
            for(String file:new String[]{"workflow-trace-"+trace.getString("traceId")+".json","workflow-trace.json"})writeAtomic(file,bytes);
        }catch(Exception e){active=false;handler.removeCallbacksAndMessages(null);
            android.widget.Toast.makeText(service,"录制存储失败，记录不可用于生成技能 / Recording storage failed",android.widget.Toast.LENGTH_LONG).show();}
    }
    private void writeAtomic(String name,byte[] bytes) throws java.io.IOException {
        if(bytes.length>262144)throw new java.io.IOException("EVIDENCE_LIMIT");
        android.util.AtomicFile file=new android.util.AtomicFile(new java.io.File(service.getFilesDir(),name));
        java.io.FileOutputStream out=file.startWrite();
        try{out.write(bytes);file.finishWrite(out);}catch(java.io.IOException e){file.failWrite(out);throw e;}
    }
}
