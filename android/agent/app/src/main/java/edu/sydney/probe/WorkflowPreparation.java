package edu.sydney.probe;

import android.content.Intent;
import android.os.*;
import android.view.accessibility.AccessibilityNodeInfo;
import org.json.*;

/** Preflight uses only public controls. It never saves, cancels edits, or resets a fixture. */
final class WorkflowPreparation {
    private final ProbeService service;
    private final Handler handler=new Handler(Looper.getMainLooper());
    private final boolean recording;
    private final String goal,source,approved;
    private final ParameterExecution invocation;
    private final WorkflowPreparationPolicy policy;
    private final JSONObject audit=new JSONObject();
    private final String id=java.util.UUID.randomUUID().toString();
    private final Runnable tick=this::poll;
    private String decision="WAIT",previousEvidence="",snapshot;
    private String observationReason="";
    private boolean active=true,terminal;
    private long nextNavigation;
    private int navigations;
    WorkflowPreparation(ProbeService service,boolean recording,String goal,String source,String approved){
        this(service,recording,goal,source,approved,null);
    }
    WorkflowPreparation(ProbeService service,boolean recording,String goal,String source,String approved,ParameterExecution invocation){
        this.service=service;this.recording=recording;this.goal=goal;this.source=source;this.approved=approved;
        this.invocation=invocation;
        try{
            String page=recording?"":WorkflowCodec.decode(approved).optString("startPage","overview");
            policy=new WorkflowPreparationPolicy(SystemClock.elapsedRealtime(),page);
            audit.put("kind","WORKFLOW_PREPARATION").put("preparationId",id).put("mode",recording?"RECORD":"RUN")
                .put("expectedPage",page).put("events",new JSONArray()).put("formalStarted",false);
        }catch(Exception e){throw new IllegalArgumentException("PREPARATION_SKILL",e);}
    }
    boolean active(){return active;}
    boolean ready(){return active&&!terminal&&decision.equals("READY");}
    void begin(){
        try{
            checkpoint("OPEN_TARGET",null);
            service.startActivity(new Intent().setClassName(WorkflowUi.PKG,WorkflowUi.PKG+".WorkflowActivity").addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
            service.teachingControls().showPreparation(recording);
            handler.postDelayed(tick,200);
        }catch(Exception e){fail("PREPARATION_OPEN_FAILED");cancel();service.teachingControls().remove();throw new IllegalStateException("PREPARATION_OPEN_FAILED",e);}
    }
    private void poll(){
        if(!active||terminal)return;
        try{
            String foreground=WorkflowForeground.read(service);
            if("OTHER".equals(foreground)){fail("LEFT_ALLOWED_APPS");return;}
            JSONObject now=null;
            try{now=WorkflowUi.snapshot(service);observationReason="";}
            catch(IllegalStateException unavailable){observationReason=String.valueOf(unavailable.getMessage());if(observationReason.length()>160)observationReason=observationReason.substring(0,160);}
            long clock=SystemClock.elapsedRealtime();
            snapshot=now==null?null:now.toString();
            decision=policy.observe(clock,now==null?null:now.getString("page"),now!=null&&now.getBoolean("dirty"),snapshot);
            if(decision.equals("READY")&&!audit.has("deviceContext")){
                audit.put("deviceContext",AndroidDeviceContext.capture(service,WorkflowUi.PKG));
                audit.put("semanticRegistry",DeviceContextCodec.registryReceipt());
            }
            checkpoint(decision,now);
            if(decision.equals("TIMED_OUT")){terminal=true;return;}
            if(java.util.List.of("RETURN_OVERVIEW","SWITCH_SINGLE","SWITCH_PAGES").contains(decision)&&clock>=nextNavigation){
                if(navigations>=4){fail("PREPARATION_NAVIGATION_UNCONFIRMED");return;}
                // Re-check before each preparation input; observing a clean child is insufficient if edits arrived since.
                JSONObject fresh=WorkflowUi.snapshot(service);
                if(!fresh.toString().equals(snapshot)||fresh.getBoolean("dirty")){snapshot=null;decision="STABILIZING";}
                else {
                    String key=decision.equals("RETURN_OVERVIEW")?(fresh.getString("page").equals("lamp")?"wfLampBack":"wfFanBack"):
                        decision.equals("SWITCH_SINGLE")?"wfSingle":"wfMulti";
                    AccessibilityNodeInfo n=WorkflowUi.observedNode(service,key);
                    if(!n.isVisibleToUser()){
                        if(!n.performAction(AccessibilityNodeInfo.AccessibilityAction.ACTION_SHOW_ON_SCREEN.getId())){fail("PREPARATION_CONTROL_HIDDEN");return;}
                    }else{
                        if(!n.isEnabled()||!n.isClickable()||!n.performAction(AccessibilityNodeInfo.ACTION_CLICK)){fail("PREPARATION_INPUT_REJECTED");return;}
                        navigations++;checkpoint("NAVIGATE:"+key,fresh);
                    }
                    nextNavigation=clock+600;
                }
            }
        }catch(Exception e){fail("PREPARATION_CHECK_FAILED");return;}
        handler.postDelayed(tick,250);
    }
    void start(){
        if(!ready())return;
        try{
            JSONObject fresh=WorkflowUi.snapshot(service);
            if(!policy.mayStart(SystemClock.elapsedRealtime(),fresh.getString("page"),fresh.getBoolean("dirty"),fresh.toString())){
                decision="STABILIZING";snapshot=null;policy.observe(SystemClock.elapsedRealtime(),null,false,null);return;
            }
            if(!recording&&(invocation==null?!approved.equals(new WorkflowStore(service).approved()):!invocation.current())){fail("SKILL_CHANGED");return;}
            checkpoint("START_REQUESTED",fresh);handler.removeCallbacksAndMessages(null);
            // Cancel the preparation before runWorkflow's stopAll, so it cannot cancel its successor.
            active=false;policy.cancel();
            if(recording){service.workflowRecorder().startPrepared(goal,source,fresh.toString());service.teachingControls().show(true);}
            else{if(invocation==null)service.runWorkflow();else service.runParameters(invocation);service.teachingControls().show(false);}
            audit.put("formalStarted",true).put("formalId",recording?service.workflowRecorder().traceId():ExecutionResultData.latestRunId(service));
            checkpoint("STARTED",fresh);
        }catch(Exception e){service.stopAll();active=true;fail("PREPARATION_START_FAILED");service.teachingControls().showPreparation(recording);}
    }
    void cancel(){if(!active)return;active=false;policy.cancel();handler.removeCallbacksAndMessages(null);try{checkpoint("CANCELLED",null);}catch(Exception ignored){}}
    private void fail(String reason){decision=reason;terminal=true;policy.cancel();handler.removeCallbacksAndMessages(null);try{checkpoint(reason,null);}catch(Exception ignored){}}
    String title(boolean en){return ready()?(en?"Ready — not started yet":"已准备好 · 尚未开始"):
        decision.equals("UNSAVED")?(en?"Unsaved edits — not started":"有未保存修改 · 尚未开始"):
        terminal?(en?"Preparation stopped — nothing started":"准备已停止 · 尚未开始"):(en?"Preparing — nothing started":"准备中 · 尚未开始");}
    String hint(boolean en){
        if(decision.equals("UNSAVED"))return en?"Save or cancel edits on the page yourself. In Single, lamp and fan must each be saved. These actions are NOT being recorded.":"请先在原页面保存或取消修改。Single 中灯和风扇要分别保存。这些准备操作尚未录制。";
        if(ready())return en?(recording?"Keep Single or Pages, then tap Start recording. Wait for Recording before demonstrating.":"At the skill's start page. Tap Start execution to run the reviewed steps."):
            (recording?"可保持 Single 或 Pages。点“开始录制”，看到“正在录制”再示范。":"已到技能起始页面。点“开始执行”后才会按指南操作。");
        if(terminal)return (en?"Nothing started. Return and try again. Code: ":"未开始正式任务，请返回后重试。原因：")+decision;
        return en?"Checking saved state and start page. No automatic save or discard. You may cancel at any time.":"正在检查保存状态和起始页面，不会自动保存或丢弃修改。可随时返回取消。";
    }
    private void checkpoint(String event,JSONObject now)throws Exception{
        String evidence=event+":"+observationReason+":"+(now==null?"":now.toString());if(evidence.equals(previousEvidence))return;
        audit.getJSONArray("events").put(new JSONObject().put("event",event).put("elapsedRealtimeMs",SystemClock.elapsedRealtime())
            .put("observation",now==null?JSONObject.NULL:now).put("observationReason",observationReason));
        byte[] data=audit.toString().getBytes(java.nio.charset.StandardCharsets.UTF_8);
        if(data.length>262144)throw new IllegalStateException("PREPARATION_EVIDENCE_LIMIT");
        android.util.AtomicFile file=new android.util.AtomicFile(new java.io.File(service.getFilesDir(),"workflow-preparation-"+id+".json"));
        java.io.FileOutputStream out=file.startWrite();try{out.write(data);file.finishWrite(out);}catch(Exception e){file.failWrite(out);throw e;}
        previousEvidence=evidence;
    }
}
