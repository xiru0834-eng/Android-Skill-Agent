package edu.sydney.probe;

import android.os.*;
import android.view.accessibility.AccessibilityNodeInfo;
import org.json.*;

/** Executes only the locally approved file; no experimental goal arguments. */
final class WorkflowRunner {
    // Frozen separately for baseline/candidate APKs; never taken from skill or remote input.
    static final boolean GUARDED_STARTUP=false;
    static final boolean FAST_INVALID_START=true;
    static final boolean RECOVER_MISSING=false;
    static final boolean RECOVER_STALE=false;
    private final ProbeService service;
    private final WorkflowStore store;
    private final Handler handler=new Handler(Looper.getMainLooper());
    private JSONObject skill;
    private JSONArray actions,boundGoals;
    private Integer[] requested;
    private String approvedSnapshot,runId;
    private ParameterExecution parameterExecution;
    private JSONObject deviceContext;
    private long started,deadline,waitUntil;
    private int index,observations,phase;
    private boolean active;
    private boolean allAlreadyAtTargets;
    private WorkflowJournal journal;
    private WorkflowStartup startup;
    private long startupReadyAt;
    private long beforeObservationMs,verificationObservationMs;
    private final WorkflowRecovery recovery=new WorkflowRecovery();
    private final WorkflowProfile profile=new WorkflowProfile();
    private int recoveryReads;
    private FlexibleWorkflow.State flexibleState;
    private int revealStep=-1,reveals;
    private long revealUntil;
    private WorkflowResources resources;
    WorkflowRunner(ProbeService s){service=s;store=new WorkflowStore(s);}
    boolean active(){return active;}
    void start() {
        start(null);
    }
    void start(ParameterExecution invocation) {
        parameterExecution=invocation;
        approvedSnapshot=invocation==null?store.approved():invocation.plan;
        if(approvedSnapshot==null||!store.sameVersion(approvedSnapshot)||(invocation!=null&&!invocation.current()))throw new IllegalStateException("NO_COMPATIBLE_APPROVAL");
        skill=WorkflowCodec.decode(approvedSnapshot);actions=new JSONArray();index=observations=phase=0;
        boundGoals=null;
        try{requested=WorkflowCodec.requested(skill.getJSONArray("finalGoals"));}catch(JSONException e){throw new IllegalArgumentException("GOALS",e);}
        recovery.clear();recoveryReads=0;profile.reset();beforeObservationMs=verificationObservationMs=0;allAlreadyAtTargets=false;
        flexibleState=null;revealStep=-1;reveals=0;revealUntil=0;
        resources=WorkflowResourceStore.read(service);
        deviceContext=AndroidDeviceContext.capture(service,WorkflowUi.PKG);
        started=SystemClock.elapsedRealtime();deadline=started+(skill.optInt("version")==3?resources.runMs(skill.optJSONArray("steps").length()):30000);waitUntil=started+4000;active=true;runId=java.util.UUID.randomUUID().toString();
        startup=new WorkflowStartup(started,deadline);startupReadyAt=0;
        if(GUARDED_STARTUP)waitUntil=startup.until();
        journal=new WorkflowJournal(service,runId);note("START",skill);
        try{note("DEVICE_CONTEXT",new JSONObject().put("deviceContext",deviceContext).put("semanticRegistry",DeviceContextCodec.registryReceipt()));}
        catch(JSONException error){active=false;throw new IllegalStateException("DEVICE_CONTEXT_AUDIT_FAILED",error);}
        if(invocation!=null)try{note("PARAMETER_CALLS",invocation.audit());}catch(Exception e){active=false;throw new IllegalStateException("PARAMETER_AUDIT_UNAVAILABLE",e);}
        persist("RUNNING","STARTING");handler.postDelayed(this::tick,900);
    }
    void cancel(){if(active)finish("CANCELLED","USER_OR_SERVICE_STOP");}
    private void tick() {
        if(!active)return;
        boolean completePrecondition=false;
        try {
            long now=SystemClock.elapsedRealtime();if(now>=deadline)throw new IllegalStateException("TASK_TIMEOUT");
            if(parameterExecution==null?!approvedSnapshot.equals(store.approved()):!parameterExecution.current())throw new IllegalStateException("APPROVAL_CHANGED");
            if(phase==1&&recovery.active()&&now>=recovery.until())throw new IllegalStateException("RECOVERY_TIMEOUT");
            observations++;
            if(skill.optInt("version")==3){tickFlexible();return;}
            if(phase==0) {
                if(GUARDED_STARTUP&&now>=startup.until())throw new IllegalStateException("STARTUP_TIMEOUT");
                JSONObject initial=observe();
                if(!initial.getString("page").equals("overview")||initial.getBoolean("dirty"))throw new IllegalStateException("INVALID_START");
                if(GUARDED_STARTUP&&!startup.ready(SystemClock.elapsedRealtime(),initial.toString())){handler.postDelayed(this::tick,100);return;}
                startupReadyAt=SystemClock.elapsedRealtime();
                note("STARTUP_READY",new JSONObject().put("elapsedMs",startupReadyAt-started).put("remainingMs",deadline-startupReadyAt));
                boundGoals=new JSONArray();for(int value:WorkflowGoals.bind(requested,WorkflowCodec.concrete(initial.getJSONArray("saved"))))boundGoals.put(value);
                note("GOALS_BOUND",new JSONObject().put("requested",skill.getJSONArray("finalGoals")).put("initial",initial.getJSONArray("saved")).put("resolved",boundGoals));
                if(same(initial.getJSONArray("saved"),boundGoals)){phase=3;handler.postDelayed(this::tick,180);return;}
                phase=1;
            }
            if(phase==3) {
                JSONObject finalState=observe();
                if(!finalState.getString("page").equals("overview")||finalState.getBoolean("dirty")||!same(finalState.getJSONArray("saved"),boundGoals))throw new IllegalStateException("FINAL_TARGET_MISMATCH");
                WorkflowTiming.requireBeforeDeadline(SystemClock.elapsedRealtime(),deadline);
                finish("SUCCEEDED","ALL_TARGETS_VERIFIED");return;
            }
            JSONObject step=skill.getJSONArray("steps").getJSONObject(index);
            if(phase==2) {
                JSONObject after=observe();boolean done=after.getString("page").equals(step.getString("afterPage"));
                if(!step.isNull("desired"))done &= after.getJSONObject("values").opt(step.getString("id")) instanceof Boolean && after.getJSONObject("values").getBoolean(step.getString("id"))==step.getBoolean("desired");
                if(done&&step.getString("id").endsWith("Save")) {
                    int g=step.getString("id").contains("Lamp")?0:2;JSONArray saved=after.getJSONArray("saved"),goals=boundGoals;
                    if(!WorkflowGoals.preserved(requested,WorkflowCodec.concrete(boundGoals),WorkflowCodec.concrete(saved)))throw new IllegalStateException("UNTOUCHED_TARGET_CHANGED");
                    done=saved.length()==4&&saved.getInt(g)==goals.getInt(g)&&saved.getInt(g+1)==goals.getInt(g+1)&&!after.getBoolean("dirty");
                }
                if(!done){if(SystemClock.elapsedRealtime()>=waitUntil)throw new IllegalStateException("STEP_UNCONFIRMED");handler.postDelayed(this::tick,100);return;}
                note("STEP_CONFIRMED",step);index++;phase=index==skill.getJSONArray("steps").length()?3:1;handler.postDelayed(this::tick,120);return;
            }
            JSONObject before=observe();
            if(!before.getString("page").equals(step.getString("page")))throw new IllegalStateException("WRONG_PAGE");
            if(index%4==1&&before.getBoolean("dirty"))throw new IllegalStateException("UNSAVED_USER_EDITS");
            completePrecondition=true;
            AccessibilityBindingResolver.Resolved permit=targetNode(step.getString("id"));
            AccessibilityNodeInfo node=permit.node;
            if(!node.isEnabled()||!node.isClickable())throw new IllegalStateException("NOT_CLICKABLE");
            if(recovery.active()) {
                if(SystemClock.elapsedRealtime()>=recovery.until())throw new IllegalStateException("RECOVERY_TIMEOUT");
                note("RECOVERY_LOCATED",new JSONObject().put("id",step.getString("id")).put("untilMs",recovery.until()));
                recovery.clear();
            }
            if(!step.isNull("desired")) {
                if(!node.isCheckable())throw new IllegalStateException("NOT_CHECKABLE");
                if(node.isChecked()==step.getBoolean("desired")){
                    waitUntil=WorkflowTiming.confirmationDeadline(SystemClock.elapsedRealtime(),deadline);phase=2;
                    note("SKIP_ALREADY_AT_TARGET",step);handler.postDelayed(this::tick,30);return;
                }
            }
            WorkflowTiming.requireBeforeDeadline(SystemClock.elapsedRealtime(),deadline);
            note("INPUT_REQUEST",step);
            long dispatchedAt=SystemClock.elapsedRealtime();
            if(dispatchedAt>=deadline){note("INPUT_ABORTED",new JSONObject().put("id",step.getString("id")).put("reason","TASK_TIMEOUT"));throw new IllegalStateException("TASK_TIMEOUT");}
            phase=2;waitUntil=WorkflowTiming.confirmationDeadline(dispatchedAt,deadline);
            actions.put(new JSONObject().put("ms",dispatchedAt).put("id",step.getString("id")).put("sourceIndex",step.getInt("sourceIndex")));
            boolean accepted;
            long inputBegan=SystemClock.elapsedRealtime();
            try{accepted=WorkflowUi.click(service,permit,deadline);}
            finally{profile.record(WorkflowProfile.Part.INPUT,SystemClock.elapsedRealtime()-inputBegan);}
            note("INPUT_RETURN",new JSONObject().put("accepted",accepted).put("dispatchedMs",dispatchedAt).put("confirmationDeadlineMs",waitUntil));
            if(!accepted)throw new IllegalStateException("INPUT_REJECTED");
            handler.postDelayed(this::tick,160);
        }catch(Exception error) {
            if("JOURNAL_UNAVAILABLE".equals(error.getMessage())){active=false;handler.removeCallbacksAndMessages(null);persist("UNCONFIRMED","JOURNAL_UNAVAILABLE");return;}
            String observedReason=error.getMessage(),focusedOwner="NOT_CHECKED";
            if(skill.optInt("version")==3&&"MISSING:wfReady".equals(observedReason)){
                focusedOwner=WorkflowForeground.read(service);
                String resolved=WorkflowObservationReason.resolve(observedReason,focusedOwner,true);
                if(!observedReason.equals(resolved))error=new IllegalStateException(resolved,error);
            }
            String rootKind=error instanceof WorkflowUi.WrongApp?((WorkflowUi.WrongApp)error).rootKind:("OTHER".equals(focusedOwner)?"OTHER":("NOT_READY".equals(error.getMessage())?"TARGET":"UNKNOWN"));
            try{JSONObject diagnostic=new JSONObject().put("reason",error.getMessage()).put("rootKind",rootKind)
                .put("windowId",error instanceof WorkflowUi.WrongApp?((WorkflowUi.WrongApp)error).windowId:-1)
                .put("remainingMs",Math.max(0,deadline-SystemClock.elapsedRealtime()));
                if(!"NOT_CHECKED".equals(focusedOwner))diagnostic.put("observedReason",observedReason).put("focusedOwner",focusedOwner);
                note("ERROR",diagnostic);}
            catch(Exception failure){active=false;handler.removeCallbacksAndMessages(null);persist("UNCONFIRMED","JOURNAL_UNAVAILABLE");return;}
            if(skill.optInt("version")==3&&java.util.List.of("INPUT_REJECTED","STEP_METADATA_CHANGED","TARGET_NOT_VISIBLE","STEP_UNCONFIRMED").contains(String.valueOf(error.getMessage()))){
                finish("UNCONFIRMED",error.getMessage());return;
            }
            // A complete but invalid starting state is not a missing/transient observation.
            if(FAST_INVALID_START&&WorkflowStartup.invalidStart(phase,error.getMessage())){
                finish("UNCONFIRMED","INVALID_START");return;
            }
            if(RECOVER_MISSING&&phase==1) {
                String id=skill.optJSONArray("steps").optJSONObject(index).optString("id");
                if((completePrecondition&&recovery.waitFor(SystemClock.elapsedRealtime(),deadline,phase,id,error.getMessage()))
                    ||(RECOVER_STALE&&recovery.retryStale(SystemClock.elapsedRealtime(),deadline,phase,error.getMessage()))) {
                    recoveryReads++;
                    try{note("RECOVERY_WAIT",new JSONObject(java.util.Map.of("id",id,"untilMs",recovery.until(),"read",recoveryReads)));}
                    catch(Exception failure){active=false;handler.removeCallbacksAndMessages(null);persist("UNCONFIRMED","JOURNAL_UNAVAILABLE");return;}
                    handler.postDelayed(this::tick,100);return;
                }
            }
            if(GUARDED_STARTUP&&phase==0){
                startup.interrupted();
                if(startup.canRetry(SystemClock.elapsedRealtime(),error.getMessage(),rootKind))handler.postDelayed(this::tick,100);
                else finish("UNCONFIRMED",error.getMessage()==null?"OBSERVATION_ERROR":error.getMessage());
                return;
            }
            // A pending transition may temporarily have no usable tree; no repeated input.
            if((phase==0||phase==2)&&SystemClock.elapsedRealtime()<waitUntil&&!(phase==2&&"WRONG_APP".equals(error.getMessage()))&&!"APPROVAL_CHANGED".equals(error.getMessage())&&!"TASK_TIMEOUT".equals(error.getMessage()))handler.postDelayed(this::tick,100);
            else finish("UNCONFIRMED",error.getMessage()==null?"OBSERVATION_ERROR":error.getMessage());
        }
    }
    private void tickFlexible()throws Exception {
        if(phase==0){
            JSONObject initial=observe();
            if(!skill.getString("startPage").equals(initial.getString("page"))||initial.getBoolean("dirty"))throw new IllegalStateException("INVALID_START");
            int[] values=WorkflowCodec.concrete(initial.getJSONArray("saved"));
            flexibleState=new FlexibleWorkflow.State(skill.getString("startPage"),values);
            if(!FlexibleWorkflowCodec.matches(initial,flexibleState))throw new IllegalStateException("INVALID_START");
            boundGoals=new JSONArray();for(int v:WorkflowGoals.bind(requested,values))boundGoals.put(v);
            note("GOALS_BOUND",new JSONObject().put("requested",skill.getJSONArray("finalGoals")).put("initial",initial.getJSONArray("saved")).put("resolved",boundGoals));
            startupReadyAt=SystemClock.elapsedRealtime();phase=1;
            if(parameterExecution!=null&&parameterExecution.noActionRequired(values)){
                // Every ordered call must already hold; final-goal equality alone is insufficient.
                index=skill.getJSONArray("steps").length();phase=3;allAlreadyAtTargets=true;
                note("NO_ACTION_REQUIRED",new JSONObject().put("reason","EVERY_ORDERED_CALL_ALREADY_AT_TARGET"));
                handler.postDelayed(this::tick,100);return;
            }
        }
        if(phase==3){
            JSONObject finalState=observe();
            if(!ParameterOutcome.canFinish(allAlreadyAtTargets,flexibleState.complete(),FlexibleWorkflowCodec.matches(finalState,flexibleState),same(finalState.getJSONArray("saved"),boundGoals)))throw new IllegalStateException("FINAL_TARGET_MISMATCH");
            WorkflowTiming.requireBeforeDeadline(SystemClock.elapsedRealtime(),deadline);finish("SUCCEEDED",allAlreadyAtTargets?"ALL_CALLS_ALREADY_AT_TARGET_VERIFIED":"ORDERED_PROCESS_AND_TARGETS_VERIFIED");return;
        }
        JSONObject step=skill.getJSONArray("steps").getJSONObject(index);
        JSONObject actual=observe();
        if(phase==2){
            long observedAt=SystemClock.elapsedRealtime();
            note("CONFIRMATION_CHECK",new JSONObject().put("sourceIndex",step.getInt("sourceIndex"))
                .put("observedMs",observedAt).put("confirmationDeadlineMs",waitUntil).put("taskDeadlineMs",deadline));
            WorkflowTiming.requireConfirmation(observedAt,waitUntil,deadline);
            if(!FlexibleWorkflowCodec.matches(actual,flexibleState)){
                if(SystemClock.elapsedRealtime()>=waitUntil)throw new IllegalStateException("STEP_UNCONFIRMED");
                handler.postDelayed(this::tick,100);return;
            }
            note("STEP_CONFIRMED",step);index++;phase=index==skill.getJSONArray("steps").length()?3:1;handler.postDelayed(this::tick,100);return;
        }
        if(!FlexibleWorkflowCodec.matches(actual,flexibleState)||!step.getString("page").equals(actual.getString("page")))throw new IllegalStateException("STEP_PRECONDITION_CHANGED");
        String id=step.getString("id");Boolean desired=step.isNull("desired")?null:step.getBoolean("desired");
        AccessibilityNodeInfo node=WorkflowUi.observedNode(service,id);
        if(!node.isVisibleToUser()){
            if(revealStep!=index){
                revealStep=index;revealUntil=Math.min(deadline,SystemClock.elapsedRealtime()+1200);reveals++;
                // Android API 23+, available at this app's minSdk 30. No coordinate fallback.
                // https://developer.android.com/reference/android/view/accessibility/AccessibilityNodeInfo.AccessibilityAction#ACTION_SHOW_ON_SCREEN
                WorkflowTiming.requireBeforeDeadline(SystemClock.elapsedRealtime(),deadline);
                boolean accepted=node.performAction(AccessibilityNodeInfo.AccessibilityAction.ACTION_SHOW_ON_SCREEN.getId());
                note("REVEAL_REQUEST",new JSONObject().put("id",id).put("accepted",accepted).put("untilMs",revealUntil));
                if(!accepted)throw new IllegalStateException("TARGET_NOT_VISIBLE");
            }
            if(SystemClock.elapsedRealtime()>=revealUntil)throw new IllegalStateException("TARGET_NOT_VISIBLE");
            handler.postDelayed(this::tick,100);return;
        }
        AccessibilityBindingResolver.Resolved permit=targetNode(id);node=permit.node;
        if(!node.isEnabled()||!node.isClickable())throw new IllegalStateException("NOT_CLICKABLE");
        boolean skip=desired!=null&&node.isCheckable()&&node.isChecked()==desired;
        if(desired!=null&&!node.isCheckable())throw new IllegalStateException("NOT_CHECKABLE");
        FlexibleWorkflow.Action transition=flexibleState.apply(id,desired);
        if(!transition.operation.equals(step.getString("operation"))||!java.util.Arrays.equals(transition.commitGoals,WorkflowCodec.requested(step.getJSONArray("commitGoals"))))throw new IllegalStateException("STEP_METADATA_CHANGED");
        phase=2;long dispatched=SystemClock.elapsedRealtime();
        waitUntil=Math.min(deadline,dispatched+resources.confirmationMs());
        if(skip){note("SKIP_ALREADY_AT_TARGET",step);handler.postDelayed(this::tick,30);return;}
        WorkflowTiming.requireBeforeDeadline(dispatched,deadline);note("INPUT_REQUEST",step);
        dispatched=SystemClock.elapsedRealtime();WorkflowTiming.requireBeforeDeadline(dispatched,deadline);
        actions.put(new JSONObject().put("ms",dispatched).put("id",id).put("sourceIndex",step.getInt("sourceIndex")));
        boolean accepted;long began=SystemClock.elapsedRealtime();
        try{accepted=WorkflowUi.click(service,permit,deadline);}finally{profile.record(WorkflowProfile.Part.INPUT,SystemClock.elapsedRealtime()-began);}
        note("INPUT_RETURN",new JSONObject().put("accepted",accepted).put("dispatchedMs",dispatched).put("confirmationDeadlineMs",waitUntil));
        if(!accepted)throw new IllegalStateException("INPUT_REJECTED");handler.postDelayed(this::tick,180);
    }
    private void note(String kind,JSONObject data){
        long began=SystemClock.elapsedRealtime();
        try{journal.add(kind,index,phase,data);}
        finally{profile.record(WorkflowProfile.Part.JOURNAL,SystemClock.elapsedRealtime()-began);}
    }
    private AccessibilityBindingResolver.Resolved targetNode(String id){
        long began=SystemClock.elapsedRealtime();
        AccessibilityBindingResolver.Resolved resolved;
        try{resolved=WorkflowUi.resolveNode(service,id);}
        finally{profile.record(WorkflowProfile.Part.TARGET_LOOKUP,SystemClock.elapsedRealtime()-began);}
        try{note("TARGET_RESOLVED",new JSONObject().put("id",id).put("strategy",resolved.strategy).put("page",resolved.page).put("windowId",resolved.node.getWindowId()));}
        catch(JSONException error){throw new IllegalStateException("RESOLUTION_AUDIT_UNAVAILABLE",error);}
        return resolved;
    }
    private JSONObject observe(){
        JSONObject value;long began=SystemClock.elapsedRealtime();
        try{value=WorkflowUi.snapshot(service);}
        finally{long elapsed=SystemClock.elapsedRealtime()-began;profile.record(WorkflowProfile.Part.SNAPSHOT,elapsed);
            if(phase==2||phase==3)verificationObservationMs+=elapsed;else beforeObservationMs+=elapsed;}
        note("OBSERVATION",value);return value;
    }
    private JSONObject profilePrefix()throws JSONException{
        JSONObject out=new JSONObject().put("scope","before this RESULT journal and result-file writes; non-overlapping measured sections only");
        for(WorkflowProfile.Part part:WorkflowProfile.Part.values()){
            long[] v=profile.values(part);
            out.put(part.name(),new JSONObject().put("count",v[0]).put("totalMs",v[1]).put("maxMs",v[2]));
        }
        return out;
    }
    private boolean same(JSONArray a,JSONArray b){return a.toString().equals(b.toString());}
    private void finish(String status,String reason){active=false;handler.removeCallbacksAndMessages(null);persist(status,reason);}
    private void persist(String status,String reason) {
        try {
            long finishedAt=SystemClock.elapsedRealtime();
            if("SUCCEEDED".equals(status)&&!WorkflowTiming.canReportSuccess(finishedAt,deadline)){status="UNCONFIRMED";reason="TASK_TIMEOUT";}
            JSONObject result=new JSONObject().put("runId",runId).put("status",status).put("reason",reason).put("startedMs",started)
                .put("finishedMs",finishedAt).put("deadlineMs",deadline).put("actions",actions).put("observations",observations)
                .put("completedSteps",index).put("traceId",skill.getString("traceId")).put("traceSha256",skill.getString("traceSha256")).put("goal",boundGoals==null?JSONObject.NULL:boundGoals).put("requestedGoals",skill.getJSONArray("finalGoals"))
                .put("startupPolicy",GUARDED_STARTUP?"C1":FAST_INVALID_START?"C2":"B0").put("startupReadyMs",startupReadyAt==0?JSONObject.NULL:startupReadyAt-started);
            result.put("profilePrefix",profilePrefix());
            result.put("visibilityAssists",reveals);
            result.put("deviceContext",deviceContext).put("semanticRegistrySha256",SemanticSkills.registryHash());
            if(parameterExecution!=null)result.put("executionMode","PARAMETERIZED").put("sourceSkillId",parameterExecution.sourceId).put("parameterInvocation",parameterExecution.audit())
                .put("parameterStatus",ParameterOutcome.status(status,reason,actions.length()))
                .put("failureStage","SUCCEEDED".equals(status)?JSONObject.NULL:ParameterOutcome.stage(reason,phase));
            if(parameterExecution!=null)result.put("skippedCompiledSteps",allAlreadyAtTargets?skill.getJSONArray("steps").length():0);
            if(parameterExecution!=null)result.put("parameterTiming",new JSONObject()
                .put("gptParsingMs",JSONObject.NULL).put("localPreflightMs",parameterExecution.localPreflightMs)
                .put("bindingResolutionMs",profile.values(WorkflowProfile.Part.TARGET_LOOKUP)[1])
                .put("uiInputCallMs",profile.values(WorkflowProfile.Part.INPUT)[1])
                .put("verificationObservationMs",verificationObservationMs).put("preconditionObservationMs",beforeObservationMs)
                .put("runtimeTotalMs",finishedAt-started)
                .put("scope","Measured call sections; not exhaustive stages. Excludes user confirmation and GPT. Observation subsets split SNAPSHOT; do not add to SNAPSHOT again."));
            if(skill.optInt("version")==3)result.put("resources",new JSONObject().put("recordingMinutes",resources.recordingMinutes).put("confirmationSeconds",resources.confirmationSeconds));
            result.put("recoveryPolicy",RECOVER_MISSING?(RECOVER_STALE?"R2":"R1"):"OFF").put("recoveryReads",recoveryReads)
                .put("terminalPhase",phase).put("terminalStepIndex",index)
                .put("terminalStepId",index<skill.getJSONArray("steps").length()?skill.getJSONArray("steps").getJSONObject(index).getString("id"):JSONObject.NULL);
            note("RESULT",result);store.result(result);
            for(String name:new String[]{"recorded-workflow-result.json","workflow-result-"+runId+".json"}) {
                android.util.AtomicFile file=new android.util.AtomicFile(new java.io.File(service.getFilesDir(),name));java.io.FileOutputStream out=null;
                try{out=file.startWrite();out.write(result.toString().getBytes(java.nio.charset.StandardCharsets.UTF_8));file.finishWrite(out);}
                catch(Exception error){if(out!=null)file.failWrite(out);throw error;}
            }
        }catch(Exception error){active=false;handler.removeCallbacksAndMessages(null);throw new IllegalStateException("WORKFLOW_EVIDENCE_UNAVAILABLE",error);}
    }
}
