package edu.sydney.probe;

import android.accessibilityservice.AccessibilityService;
import android.graphics.Rect;
import android.hardware.HardwareBuffer;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;
import android.view.Display;
import android.view.accessibility.AccessibilityEvent;
import android.view.accessibility.AccessibilityNodeInfo;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public final class ProbeService extends AccessibilityService {
    private static final String TAG = "DemoProbe";
    private static final int MAX_RECORDS = 100;
    private static volatile ProbeService instance;
    private volatile boolean serviceConnected;
    private static volatile String lifecycleState="NOT_CONNECTED", lifecycleFailure="";
    static org.json.JSONObject connectionAudit()throws Exception {
        var active=instance;
        return new org.json.JSONObject().put("lifecycle",lifecycleState).put("failure",lifecycleFailure)
            .put("instance_present",active!=null).put("connected_flag",active!=null&&active.serviceConnected)
            .put("service_bound",current()!=null);
    }
    private final ArrayDeque<String> records = new ArrayDeque<>();
    private final Handler handler = new Handler(Looper.getMainLooper());
    private DemoTrace trace = new DemoTrace();
    private boolean baselineReady;
    private long clickGeneration;
    private final Runnable stableObservation = this::observeStableState;
    private boolean recording;
    private long sessionId;
    private String screenshotResult = "Not tested";
    private String recordingPackage = ProbePolicy.LAB_PACKAGE;
    private ReplayRunner runner;
    private TwoStepRunner twoRunner;
    private LanguageController language;
    private WorkflowRecorder workflowRecorder;
    private WorkflowRunner workflowRunner;
    private WorkflowPreparation workflowPreparation;
    boolean workflowPreparing(){return workflowPreparation!=null&&workflowPreparation.active();}
    WorkflowPreparation workflowPreparation(){return workflowPreparation;}
    void prepareRecording(String goal,String source){stopAll();workflowPreparation=new WorkflowPreparation(this,true,goal,source,null);workflowPreparation.begin();}
    void prepareWorkflow(){String raw=new WorkflowStore(this).approved();if(raw==null)throw new IllegalStateException("NO_SKILL");stopAll();workflowPreparation=new WorkflowPreparation(this,false,null,null,raw);workflowPreparation.begin();}
    void prepareParameters(ParameterExecution invocation){if(!invocation.current())throw new IllegalStateException("PARAMETER_BINDING_CHANGED");stopAll();workflowPreparation=new WorkflowPreparation(this,false,null,null,invocation.plan,invocation);workflowPreparation.begin();}
    private java.util.concurrent.atomic.AtomicBoolean portableCancelled;
    private volatile boolean portableActive;
    private final ThreadLocal<PortableServiceAudit> portableServiceAudit = new ThreadLocal<>();
    private final java.util.concurrent.atomic.AtomicInteger unfinishedPortableWorkers=new java.util.concurrent.atomic.AtomicInteger();
    int unfinishedPortableWorkers(){return unfinishedPortableWorkers.get();}
    private volatile PortableLaunchGate portableLaunchGate;
    private volatile boolean portableWindowEventsActive;
    private String[] normalEventPackages;
    private int normalEventTypes;
    private long normalEventTimeout;
    /** Task-scoped window metadata only. Never requests an Android permission or UI content. */
    private synchronized void beginPortableWindowEvents(){
        if(portableWindowEventsActive)throw new IllegalStateException("SERVICE_UNAVAILABLE");
        var info=getServiceInfo();if(info==null)throw new IllegalStateException("SERVICE_UNAVAILABLE");
        normalEventPackages=info.packageNames==null?null:info.packageNames.clone();normalEventTypes=info.eventTypes;normalEventTimeout=info.notificationTimeout;
        portableWindowEventsActive=true;
        info.packageNames=null;
        info.eventTypes=normalEventTypes|AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED|AccessibilityEvent.TYPE_WINDOWS_CHANGED;
        info.notificationTimeout=0;
        setServiceInfo(info);
    }
    private synchronized void endPortableWindowEvents(){
        if(!portableWindowEventsActive)return;
        var info=getServiceInfo();if(info==null)return; // remain metadata-only and fail closed
        info.packageNames=normalEventPackages==null?null:normalEventPackages.clone();info.eventTypes=normalEventTypes;
        info.notificationTimeout=normalEventTimeout;
        try{setServiceInfo(info);portableWindowEventsActive=false;}
        catch(RuntimeException error){Log.e(TAG,"window event scope restoration failed");}
    }
    private synchronized java.util.Map<String,Object> portableEventScope(){
        var info=getServiceInfo();if(info==null)return java.util.Map.of("sdk_available",false,"active",portableWindowEventsActive);
        boolean restored=!portableWindowEventsActive&&info.eventTypes==normalEventTypes&&info.notificationTimeout==normalEventTimeout&&java.util.Arrays.equals(info.packageNames,normalEventPackages);
        return java.util.Map.of("sdk_available",true,"active",portableWindowEventsActive,"event_types",info.eventTypes,
            "packages_unfiltered",info.packageNames==null,"original_filter_restored",restored,"notification_timeout_ms",info.notificationTimeout);
    }
    private synchronized java.util.Map<String,Object> finishPortableEventScope(java.util.concurrent.atomic.AtomicBoolean token){
        if(portableCancelled!=token)return java.util.Map.of("task_current",false);
        portableActive=false;portableLaunchGate=null;endPortableWindowEvents();return portableEventScope();
    }
    boolean workflowRunning(){return portableActive||(workflowRunner!=null&&workflowRunner.active());}
    synchronized void runPortable(PortableSkillCodec.Package pkg,org.json.JSONArray calls,java.util.function.Consumer<org.json.JSONObject> completion)throws Exception {
        runPortableInternal(pkg,calls,null,completion);
    }
    synchronized void runFlow(org.json.JSONObject plan,java.util.Set<String> authorizedWrites,String mode,java.util.function.Consumer<org.json.JSONObject> completion)throws Exception {
        if(workflowRunning()||workflowPreparing()||isRecording())throw new IllegalStateException("SERVICE_BUSY");
        var pkg=new PortableSkillStore(this).approved();
        var flow=new FlowAndroidRunner(plan,pkg,authorizedWrites,mode);
        flow.pinLocalPublishedKnowledge(this);
        runPortableInternal(pkg,new org.json.JSONArray(),flow,completion);
    }
    /** Additive normal candidate entrance. Cancellation can only stop this launch's token. */
    synchronized Runnable runCandidateFlow(org.json.JSONObject plan,java.util.Set<String> writes,java.util.function.Consumer<org.json.JSONObject> completion)throws Exception {
        runFlow(plan,writes,"CANDIDATE_VALIDATION",completion);
        final var token=portableCancelled;
        return ()->{synchronized(ProbeService.this){if(token!=null&&portableCancelled==token&&portableActive)stopAll();}};
    }
    private synchronized void runPortableInternal(PortableSkillCodec.Package pkg,org.json.JSONArray calls,FlowAndroidRunner flow,java.util.function.Consumer<org.json.JSONObject> completion)throws Exception {
        new PortableSkillStore(this).version();if(flow==null)pkg.compile(calls);stopAll();
        var cancellation=new java.util.concurrent.atomic.AtomicBoolean();portableCancelled=cancellation;portableActive=true;
        final long launchStarted=android.os.SystemClock.elapsedRealtime();
        final var delivered=new java.util.concurrent.atomic.AtomicBoolean();
        final var audit=flow==null?null:new PortableServiceAudit(flow.data().getString("task_id"),
            flow.data().getString("flow_hash"),flow.hash(),pkg.hash,flow.data().getString("host_device_id"),
            LearningCapture.PROCESS_SESSION,launchStarted,flow.budget());
        final var viewportContexts=new PortableViewportContexts<android.content.Context>();
        if(flow!=null)flow.timing.deadline(launchStarted+flow.budget());
        final var launchGate=new PortableLaunchGate(PortableSkillCodec.PKG,launchStarted,android.os.SystemClock.uptimeMillis(),8000,getPackageName());portableLaunchGate=launchGate;
        final var observation=new PortableLaunchSession(launchGate);
        android.content.Intent intent=new android.content.Intent().setClassName(PortableSkillCodec.PKG,PortableSkillCodec.PKG+".ParameterRoomActivity").addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK);
        final var launchTiming=new java.util.LinkedHashMap<String,Object>();
        launchTiming.put("clock","ELAPSED_REALTIME_MS");launchTiming.put("task_started_ms",launchStarted);
        try{
            launchTiming.put("event_scope_started_ms",android.os.SystemClock.elapsedRealtime());beginPortableWindowEvents();
            launchTiming.put("event_scope_finished_ms",android.os.SystemClock.elapsedRealtime());
            launchTiming.put("start_activity_started_ms",android.os.SystemClock.elapsedRealtime());startActivity(intent);
            launchTiming.put("start_activity_returned_ms",android.os.SystemClock.elapsedRealtime());
        }catch(Exception e){
            if(audit==null){portableActive=false;cancellation.set(true);portableLaunchGate=null;endPortableWindowEvents();throw e;}
            emitPortableServiceFailure(audit,flow,launchGate,observation,cancellation,delivered,"SERVICE_PREPARE",false,
                null,null,launchTiming,e,completion);
            portableActive=false;portableLaunchGate=null;endPortableWindowEvents();return;
        }
        launchTiming.put("worker_dispatch_requested_ms",android.os.SystemClock.elapsedRealtime());
        unfinishedPortableWorkers.incrementAndGet();
        try{PortableWorker.start(()->{
            launchTiming.put("worker_started_ms",android.os.SystemClock.elapsedRealtime());
            org.json.JSONObject deviceContext=null, serviceResult=null;
            boolean flowEntered=false;
            String serviceStage="LAUNCH_WAIT";
            if(audit!=null)portableServiceAudit.set(audit);
            try{
                String launchState;
                while((launchState=launchGate.state(android.os.SystemClock.elapsedRealtime(),cancellation.get(),instance==this)).equals("WAIT")){
                    AccessibilityBindingResolver.Frame frame=null;
                    try{
                        frame=portableFrame(true,observation,"launch",viewportContexts);
                        if(!PortableSkillCodec.PAGE.equals(frame.page))throw new IllegalStateException("PAGE_CHANGED");
                        launchGate.observeWindow(PortableSkillCodec.PKG,frame.root.getWindowId(),android.os.SystemClock.elapsedRealtime());
                    }catch(IllegalStateException reading){
                        launchGate.invalidateWindow();String reason=reading.getMessage();
                        if(!"NO_TREE".equals(reason)&&!"LAUNCH_TRANSITION".equals(reason)&&!PortableObservationPolicy.retryObservation(reason))throw reading;
                    }finally{if(frame!=null&&frame.root!=null)frame.root.recycle();}
                    if(!launchGate.state(android.os.SystemClock.elapsedRealtime(),cancellation.get(),instance==this).equals("WAIT"))break;
                    android.os.SystemClock.sleep(Math.min(80,launchGate.remaining(android.os.SystemClock.elapsedRealtime())));
                }
                launchState=launchGate.state(android.os.SystemClock.elapsedRealtime(),cancellation.get(),instance==this);
                if(!launchState.equals("READY"))throw new IllegalStateException(launchState);
                serviceStage="ROOT_READ";
                deviceContext=AndroidDeviceContext.capture(this,PortableSkillCodec.PKG);
                final boolean[] firstRead={true};
                var runtime=new PortableSkillRuntime(pkg,()->{
                    try{boolean fresh=firstRead[0];firstRead[0]=false;return portableFrame(fresh,observation,"runtime",viewportContexts);}
                    catch(IllegalStateException stale){if("STALE_WINDOWS".equals(stale.getMessage())&&android.os.Build.VERSION.SDK_INT>=33)clearCache();throw stale;}
                },cancellation::get);
                long launchWait=android.os.SystemClock.elapsedRealtime()-launchStarted;
                int remaining=launchGate.remaining(android.os.SystemClock.elapsedRealtime());
                if(remaining<=0)throw new IllegalStateException("LAUNCH_WINDOW_UNAVAILABLE");
                serviceStage="FLOW_RUN";flowEntered=flow!=null;
                var result=flow==null?runtime.run(calls,remaining):flow.run(this,()->portableFrame(true,observation,"flow",viewportContexts),cancellation,launchStarted,()->instance==this&&portableCancelled==cancellation&&portableActive&&flow.localKnowledgeCurrent(this));
                serviceResult=result;serviceStage="SERIALIZATION";
                if(audit!=null)result.put("observation_budget",new org.json.JSONObject(audit.counters()));
                if(flow!=null)flow.timing.mark("service_json_assembly.start");
                result.put("device_context",deviceContext).put("launch_timing",new org.json.JSONObject(launchTiming)).put("launch_readiness",portableLaunchReceipt(launchGate)).put("window_read",new org.json.JSONObject(observation.latest()))
                    .put("window_read_history",new org.json.JSONArray(observation.history())).put("window_read_history_dropped",observation.dropped());
                result.getJSONObject("latency").put("launch_wait_ms",launchWait).put("launch_and_runtime_ms",android.os.SystemClock.elapsedRealtime()-launchStarted);
                if(flow!=null)flow.timing.mark("service_json_assembly.end");
                if(flow!=null)flow.timing.mark("event_scope_restore.start");
                result.put("event_scope_after",new org.json.JSONObject(finishPortableEventScope(cancellation)));
                if(flow!=null)flow.timing.mark("event_scope_restore.end");
                if(flow!=null)result.put("timing",flow.timing.receipt(flow.data().getString("task_id"),flow.hash()));
                if(flow!=null)FlowAndroidRunner.finishReceipt(result,launchStarted,launchStarted+flow.budget(),cancellation,"SERVICE_RECEIPT_READY");
                serviceStage="CALLBACK";
                if(!delivered.compareAndSet(false,true))throw new IllegalStateException("DUPLICATE_SERVICE_CALLBACK");
                completion.accept(result);
            }catch(Exception e){
                if(delivered.get()){Log.e(TAG,"SERVICE_CALLBACK_DELIVERY_FAILED:"+e.getClass().getSimpleName());return;}
                if(audit!=null){
                    emitPortableServiceFailure(audit,flow,launchGate,observation,cancellation,delivered,serviceStage,
                        flowEntered,serviceResult,deviceContext,launchTiming,e,completion);return;
                }
                try{String reason=e.getMessage()==null?e.getClass().getSimpleName():e.getMessage();
                if("LAUNCH_WINDOW_UNAVAILABLE".equals(reason)&&!launchGate.foreignTransitionWitness(android.os.SystemClock.elapsedRealtime()).isEmpty())reason="BLOCKED_BY_OVERLAY";
                completion.accept(new org.json.JSONObject().put("run_id",java.util.UUID.randomUUID().toString()).put("package_hash",pkg.hash).put("calls",calls)
                .put("initial_state",new org.json.JSONObject()).put("final_observed_state",new org.json.JSONObject()).put("final_observation_complete",false).put("execution_actions",new org.json.JSONArray()).put("observations",new org.json.JSONArray()).put("resolved_element",new org.json.JSONArray())
                .put("verification_result",false).put("failure_stage","resolution").put("final_status",flow!=null&&"CANCELLED".equals(reason)?"CANCELLED":PortableObservationPolicy.failureStatus("resolution",reason)).put("reason",reason)
                .put("device_context",deviceContext==null?AndroidDeviceContext.capture(this,PortableSkillCodec.PKG):deviceContext).put("launch_timing",new org.json.JSONObject(launchTiming)).put("launch_readiness",portableLaunchReceipt(launchGate)).put("window_read",new org.json.JSONObject(observation.latest()))
                .put("window_read_history",new org.json.JSONArray(observation.history())).put("window_read_history_dropped",observation.dropped())
                .put("latency",new org.json.JSONObject().put("runtime_ms",0).put("launch_wait_ms",android.os.SystemClock.elapsedRealtime()-launchStarted).put("launch_and_runtime_ms",android.os.SystemClock.elapsedRealtime()-launchStarted))
                .put("event_scope_after",new org.json.JSONObject(finishPortableEventScope(cancellation))));}catch(Exception ignored){}}
            finally{try{portableServiceAudit.remove();viewportContexts.clear();synchronized(this){if(portableCancelled==cancellation){portableActive=false;portableLaunchGate=null;endPortableWindowEvents();}}}
                finally{unfinishedPortableWorkers.decrementAndGet();}}
        });}catch(Exception workerFailure){
            unfinishedPortableWorkers.decrementAndGet();
            if(audit==null)throw workerFailure;
            emitPortableServiceFailure(audit,flow,launchGate,observation,cancellation,delivered,"SERVICE_PREPARE",false,
                null,null,launchTiming,workerFailure,completion);
            portableActive=false;portableLaunchGate=null;endPortableWindowEvents();
        } // No extra UI-queue hop. The gate still enforces the 500ms input floor.
    }
    /** Read-only DUMP audit metadata at the normal Probe start page. Never reads Root. */
    org.json.JSONObject admissionWindowMetadata()throws org.json.JSONException{
        long start=android.os.SystemClock.elapsedRealtime();
        var out=new org.json.JSONObject().put("clock","ELAPSED_REALTIME_MS").put("started_ms",start)
            .put("root_requested",false).put("windows_attempts",1).put("process_session",LearningCapture.PROCESS_SESSION);
        java.util.List<android.view.accessibility.AccessibilityWindowInfo> windows=null;
        try{
            windows=getWindows();if(windows==null)throw new IllegalStateException("WINDOWS_NULL");
            var nodes=new org.json.JSONArray();int apps=0;
            for(var w:windows){if(w.getType()==android.view.accessibility.AccessibilityWindowInfo.TYPE_APPLICATION)apps++;
                nodes.put(new org.json.JSONObject().put("id",w.getId()).put("type",w.getType())
                    .put("active",w.isActive()).put("focused",w.isFocused()).put("layer",w.getLayer()));}
            out.put("status","CAPTURED").put("application_windows",apps).put("windows",nodes);
        }catch(Exception error){out.put("status","WINDOW_METADATA_ERROR").put("reason",error.getClass().getSimpleName())
            .put("application_windows",org.json.JSONObject.NULL).put("windows",org.json.JSONObject.NULL);}
        finally{if(windows!=null)for(var w:windows)w.recycle();}
        return out.put("finished_ms",android.os.SystemClock.elapsedRealtime());
    }
    private void emitPortableServiceFailure(PortableServiceAudit audit,FlowAndroidRunner flow,PortableLaunchGate gate,
            PortableLaunchSession observation,java.util.concurrent.atomic.AtomicBoolean cancellation,
            java.util.concurrent.atomic.AtomicBoolean delivered,String stage,boolean entered,org.json.JSONObject actual,
            org.json.JSONObject context,java.util.Map<String,Object> launchTiming,Exception error,
            java.util.function.Consumer<org.json.JSONObject> completion){
        try{
            String reason=error.getMessage()==null?error.getClass().getSimpleName():error.getMessage();
            if("LAUNCH_WINDOW_UNAVAILABLE".equals(reason)&&!gate.foreignTransitionWitness(android.os.SystemClock.elapsedRealtime()).isEmpty())reason="BLOCKED_BY_OVERLAY";
            java.util.Map<String,Object> evidence=null;
            if(actual!=null){evidence=new java.util.LinkedHashMap<>();
                for(String key:java.util.List.of("initial_state","final_observed_state","execution_actions","observations","completed_steps","steps"))
                    if(actual.has(key))evidence.put(key,actual.opt(key));}
            var restored=finishPortableEventScope(cancellation);
            long finished=android.os.SystemClock.elapsedRealtime();
            var failure=new org.json.JSONObject(audit.failure(stage,reason,finished,cancellation.get(),entered,evidence))
                .put("device_context",context==null?org.json.JSONObject.NULL:context)
                .put("device_context_status",context==null?"NOT_CAPTURED":"CAPTURED")
                .put("launch_timing",new org.json.JSONObject(launchTiming)).put("launch_readiness",portableLaunchReceipt(gate))
                .put("window_read",new org.json.JSONObject(observation.latest()))
                .put("window_read_history",new org.json.JSONArray(observation.history())).put("window_read_history_dropped",observation.dropped())
                .put("event_scope_after",new org.json.JSONObject(restored));
            failure.put("unfinished_workers",unfinishedPortableWorkers.get()).put("cancellation_observed",cancellation.get());
            // Failure assembly/restore is included; use ONE final elapsed clock sample.
            long deliverySample=android.os.SystemClock.elapsedRealtime();
            String finalError=cancellation.get()?"CANCELLED":failure.getString("final_status");
            failure.put("final_status",finalError);
            failure.getJSONObject("timing").put("finished_ms",deliverySample);
            failure.getJSONObject("error_boundary").put("finished_ms",deliverySample).put("final_status",finalError);
            failure.getJSONObject("latency").put("launch_and_runtime_ms",deliverySample-((Number)launchTiming.get("task_started_ms")).longValue());
            if(!delivered.compareAndSet(false,true)){Log.e(TAG,"SERVICE_ERROR_CALLBACK_DUPLICATE_BLOCKED");return;}
            completion.accept(failure);
        }catch(Exception delivery){Log.e(TAG,"SERVICE_ERROR_RECEIPT_DELIVERY_FAILED:"+delivery.getClass().getSimpleName());}
    }
    private java.util.List<android.view.accessibility.AccessibilityWindowInfo> portableWindows(String phase){
        var audit=portableServiceAudit.get();if(audit!=null)audit.before("windows",phase);
        boolean returned=false;try{var value=getWindows();returned=true;return value;}
        finally{if(audit!=null)audit.after("windows",returned?"RETURNED":"THREW");}
    }
    private AccessibilityNodeInfo portableRoot(String phase){
        var audit=portableServiceAudit.get();if(audit!=null)audit.before("root",phase);
        boolean returned=false;try{var value=getRootInActiveWindow();returned=true;return value;}
        finally{if(audit!=null)audit.after("root",returned?"RETURNED":"THREW");}
    }
    private org.json.JSONObject portableLaunchReceipt(PortableLaunchGate gate)throws org.json.JSONException{
        return new org.json.JSONObject().put("source","FRESH_GUARDED_TARGET_WINDOW").put("stableWindowSamples",gate.observedSamples())
            .put("eventReceivedElapsedMs",gate.eventReceivedElapsed()).put("budgetMs",8000)
            .put("window_metadata",new org.json.JSONObject(gate.windowMetadata())).put("event_scope",new org.json.JSONObject(portableEventScope()))
            .put("foreign_transition_witness",new org.json.JSONObject(gate.foreignTransitionWitness(android.os.SystemClock.elapsedRealtime())));
    }
    private AccessibilityBindingResolver.Frame portableFrame(boolean fresh,PortableLaunchSession observation,String phase,PortableViewportContexts<android.content.Context> viewportContexts){
        AccessibilityNodeInfo root=null;java.util.List<android.view.accessibility.AccessibilityWindowInfo> windows=null;boolean returned=false;
        String readStatus="READ_FAILED";
        observation.beginRead(android.os.SystemClock.elapsedRealtime());observation.put("phase",phase);
        try{
            try{
                var transition=observation.gate.foreignTransitionWitness(android.os.SystemClock.elapsedRealtime());
                observation.put("foreign_transition_witness",transition);
                if(!transition.isEmpty())throw new IllegalStateException("BLOCKED_BY_OVERLAY");
                long segment=android.os.SystemClock.elapsedRealtime();
                if(fresh&&android.os.Build.VERSION.SDK_INT>=33)clearCache();
                observation.put("cache_before_ms",android.os.SystemClock.elapsedRealtime()-segment);segment=android.os.SystemClock.elapsedRealtime();
                windows=portableWindows(phase);observation.put("windows_before_ms",android.os.SystemClock.elapsedRealtime()-segment);
                int apps=0;var types=new java.util.ArrayList<Integer>();var foregroundIds=new java.util.ArrayList<Integer>();
                boolean foreign=false,knownPresent=false,ime=false;var currentGate=observation.gate;
                int known=currentGate==null?-1:currentGate.knownWindowId();
                if(windows!=null)for(var w:windows){types.add(w.getType());if(w.getType()==android.view.accessibility.AccessibilityWindowInfo.TYPE_APPLICATION){
                    apps++;knownPresent|=w.getId()==known;if(w.isActive()||w.isFocused()){foregroundIds.add(w.getId());foreign|=w.getId()!=known;}
                }else if(w.getType()==android.view.accessibility.AccessibilityWindowInfo.TYPE_INPUT_METHOD)ime=true;}
                foreign=PortableWindowReadPolicy.foreign(known,knownPresent,apps,foreign);
                observation.put("elapsed_ms",android.os.SystemClock.elapsedRealtime());
                observation.put("window_count",windows==null?-1:windows.size());observation.put("application_windows",apps);
                observation.put("types",types);observation.put("target_event_window",currentGate.eventWindowId());
                observation.put("known_target_window",known);observation.put("foreground_application_ids",foregroundIds);
                observation.put("foreign_foreground",foreign);
                var ownerWitness=currentGate.foregroundOwnerWitness(foregroundIds,android.os.SystemClock.elapsedRealtime());
                observation.put("foreground_owner_witness",ownerWitness);
                if(!ownerWitness.isEmpty())throw new IllegalStateException("BLOCKED_BY_OVERLAY");
                // A cached target ID may belong to a previous window of this same App.
                // A mismatch cannot establish ownership or authorize an input. Read current
                // Root identity, then require the existing fresh post-read window guard.
                String preFailure=PortableWindowReadPolicy.preRootFailure(windows==null?-1:windows.size(),apps,ime);
                if(!preFailure.isEmpty())throw new IllegalStateException(preFailure);
                observation.put("root_requested",true);segment=android.os.SystemClock.elapsedRealtime();root=portableRoot(phase);
                observation.put("root_binder_ms",android.os.SystemClock.elapsedRealtime()-segment);observation.put("root_readable",root!=null);
                observation.put("root_owner",PortableLaunchSession.owner(root==null?null:root.getPackageName(),PortableSkillCodec.PKG,getPackageName()));
                observation.put("root_window_id",root==null?-1:root.getWindowId());
                // Events can arrive while the Root Binder call is waiting.
                transition=observation.gate.foreignTransitionWitness(android.os.SystemClock.elapsedRealtime());
                observation.put("foreign_transition_witness",transition);
                if(!transition.isEmpty())throw new IllegalStateException("BLOCKED_BY_OVERLAY");
                if(root==null)throw new IllegalStateException(PortableWindowReadPolicy.failure(false,windows==null?-1:windows.size(),apps,!foregroundIds.isEmpty()));
            }
            catch(IllegalStateException error){throw error;}
            catch(Exception error){throw new IllegalStateException("ROOT_READ_FAILED");}
            if(fresh&&root!=null&&getPackageName().contentEquals(root.getPackageName()==null?"":root.getPackageName()))throw new IllegalStateException("LAUNCH_TRANSITION");
            // Preserve the existing package restriction even when its window metadata is absent.
            // Package identity is used only to refuse; no foreign UI content is traversed.
            if(!PortableSkillCodec.PKG.contentEquals(root.getPackageName()==null?"":root.getPackageName()))throw new IllegalStateException("BLOCKED_BY_OVERLAY");
            // Root retrieval is a Binder operation and can outlast a window transition.
            // Do not authorize the returned tree against the pre-read window snapshot.
            if(windows!=null)for(var window:windows)window.recycle();windows=null;
            try{
                long segment=android.os.SystemClock.elapsedRealtime();
                if(android.os.Build.VERSION.SDK_INT>=33)clearCache();
                observation.put("cache_after_ms",android.os.SystemClock.elapsedRealtime()-segment);segment=android.os.SystemClock.elapsedRealtime();
                windows=portableWindows(phase);observation.put("windows_after_ms",android.os.SystemClock.elapsedRealtime()-segment);
                int apps=0;boolean rootPresent=false,foreign=false,ime=false;
                var post=new java.util.ArrayList<java.util.Map<String,Object>>();
                for(var window:windows==null?java.util.List.<android.view.accessibility.AccessibilityWindowInfo>of():windows){
                    post.add(java.util.Map.of("id",window.getId(),"type",window.getType(),"layer",window.getLayer(),"active",window.isActive(),"focused",window.isFocused()));
                    if(window.getType()==android.view.accessibility.AccessibilityWindowInfo.TYPE_INPUT_METHOD)ime=true;
                    if(window.getType()==android.view.accessibility.AccessibilityWindowInfo.TYPE_APPLICATION){
                        apps++;rootPresent|=window.getId()==root.getWindowId();
                        foreign|=(window.isActive()||window.isFocused())&&window.getId()!=root.getWindowId();
                    }
                }
                observation.put("post_root_windows",post);
                observation.put("post_root_window_elapsed_ms",android.os.SystemClock.elapsedRealtime());
                String postFailure=PortableWindowReadPolicy.postRootFailure(rootPresent,windows==null?-1:apps,foreign,ime);
                if(!postFailure.isEmpty())throw new IllegalStateException(postFailure);
            }catch(IllegalStateException error){throw error;}
            catch(Exception error){throw new IllegalStateException("ROOT_READ_FAILED");}
            long windowGuardStart=android.os.SystemClock.elapsedRealtime();
            var frame=PortableWindowGuard.frame(root,windows);
            observation.put("window_guard_ms",android.os.SystemClock.elapsedRealtime()-windowGuardStart);
            if("launch".equals(phase)){
                // Window identity alone can remain stable during a cross-task translation.
                // Use this window's live display, not a saved source-device size. Retrying
                // invalidates readiness samples; the outer gate retains the original deadline.
                android.view.accessibility.AccessibilityWindowInfo targetWindow=null;
                try{
                    targetWindow=root.getWindow();
                    if(targetWindow==null)throw new IllegalStateException("NO_TREE");
                    android.view.Display display=getSystemService(android.hardware.display.DisplayManager.class).getDisplay(targetWindow.getDisplayId());
                    if(display==null)throw new IllegalStateException("DISPLAY_UNAVAILABLE");
                    long contextStart=android.os.SystemClock.elapsedRealtime();
                    // Reuse only the task's SDK context resource, not old display bounds.
                    // The current display is checked above; metrics are queried below on every read.
                    android.content.Context displayContext=viewportContexts.current(targetWindow.getDisplayId(),()->createDisplayContext(display).createWindowContext(android.view.WindowManager.LayoutParams.TYPE_ACCESSIBILITY_OVERLAY,null));
                    observation.put("viewport_context_ms",android.os.SystemClock.elapsedRealtime()-contextStart);
                    long metricsStart=android.os.SystemClock.elapsedRealtime();
                    android.graphics.Rect viewport=displayContext.getSystemService(android.view.WindowManager.class).getMaximumWindowMetrics().getBounds();
                    observation.put("viewport_metrics_ms",android.os.SystemClock.elapsedRealtime()-metricsStart);
                    android.graphics.Rect rootBounds=new android.graphics.Rect();root.getBoundsInScreen(rootBounds);
                    android.graphics.Rect windowBounds=new android.graphics.Rect();targetWindow.getBoundsInScreen(windowBounds);
                    observation.put("launch_viewport",java.util.List.of(viewport.left,viewport.top,viewport.right,viewport.bottom));
                    observation.put("launch_root_bounds",java.util.List.of(rootBounds.left,rootBounds.top,rootBounds.right,rootBounds.bottom));
                    observation.put("launch_window_bounds",java.util.List.of(windowBounds.left,windowBounds.top,windowBounds.right,windowBounds.bottom));
                    boolean inside=PortableLaunchViewport.inside(rootBounds.left,rootBounds.top,rootBounds.right,rootBounds.bottom,viewport.left,viewport.top,viewport.right,viewport.bottom)
                        && PortableLaunchViewport.inside(windowBounds.left,windowBounds.top,windowBounds.right,windowBounds.bottom,viewport.left,viewport.top,viewport.right,viewport.bottom);
                    observation.put("launch_viewport_ready",inside);
                    if(!inside)throw new IllegalStateException("LAUNCH_TRANSITION");
                }finally{if(targetWindow!=null)targetWindow.recycle();}
            }
            returned=true;readStatus="OK";return frame;
        }catch(IllegalStateException error){readStatus=error.getMessage();throw error;
        }finally{
            observation.completeRead(readStatus,android.os.SystemClock.elapsedRealtime());
            if(!returned&&root!=null)root.recycle();if(windows!=null)for(var window:windows)window.recycle();
        }
    }
    private TeachingOverlay teachingOverlay;
    TeachingOverlay teachingControls(){if(teachingOverlay==null)teachingOverlay=new TeachingOverlay(this);return teachingOverlay;}
    void runWorkflow() { stopAll();workflowRunner=new WorkflowRunner(this);workflowRunner.start(); }
    void runParameters(ParameterExecution invocation){stopAll();workflowRunner=new WorkflowRunner(this);workflowRunner.start(invocation);}
    WorkflowRecorder workflowRecorder() { if(workflowRecorder==null)workflowRecorder=new WorkflowRecorder(this);return workflowRecorder; }
    public LanguageController language() { if(language==null) language=new LanguageController(this);return language; }
    private DeploymentController deployments;
    private Runnable pendingCheck;
    private String traceId, traceGoal="", traceVersion="unknown", traceStorage="No recording in this service session";
    private TraceBundle.Source traceSource=TraceBundle.Source.UNKNOWN;

    public static ProbeService current() {
        var active=instance;
        if(active==null||!active.serviceConnected)return null;
        try{return active.getServiceInfo()==null?null:active;}
        catch(RuntimeException disconnected){return null;}
    }
    public boolean isRecording() { return recording; }
    public int count() { return records.size(); }
    public List<String> recent() { return new ArrayList<>(records); }
    public List<DemoTrace.Step> steps() { return trace.steps(); }
    public DraftSkill.Result draft() { return DraftSkill.compile(recording, trace, recordingPackage); }
    public String recordingPackage() { return recordingPackage; }
    public String traceStorage() { return traceStorage; }
    public SwitchSkill reviewedCandidate() {
        if (!"READY_FOR_REVIEW".equals(draft().code)) return null;
        DemoTrace.Step step = trace.steps().get(0);
        return new SwitchSkill(recordingPackage, step.targetId,
                "checked=true".equals(step.before), "checked=true".equals(step.after));
    }
    public void runSkill(SwitchSkill skill, boolean desired) { stopAll(); runner.start(skill, desired); }
    public void runTwo(TwoStepSkill skill, List<Boolean> desired) { stopAll(); twoRunner.start(skill, desired); }
    public DeploymentController deployments() { return deployments; }
    public void scanDeployment(String pkg) { stopAll(); deployments.scan(pkg); }
    public void checkDeployment(DeploymentSkill s) { stopAll(); deployments.check(s); }
    public void runDeployment(String bindingId,List<Boolean> desired) {
        stopAll();DeploymentSkill s=new DeploymentStore(this).active();
        if(s==null || !s.bindingId.equals(bindingId)) throw new IllegalArgumentException("Reviewed deployment changed");
        twoRunner.startDeployment(s,desired);
    }
    public String twoDraftReason() { return TwoStepDraft.reason(recording, trace, recordingPackage); }
    private void persistDrafts() {
        // The evidence workbench stages nothing implicitly, including on timeout.
        // Its explicit restore action always requires a fresh binding check and review.
        if(!traceGoal.isBlank()) return;
        new SkillStore(this).draft(recordingPackage, reviewedCandidate());
        new TwoStepStore(this).setDraft(recordingPackage, TwoStepDraft.compile(recording,trace,recordingPackage),false);
    }
    public synchronized void stopAll() {
        if(portableCancelled!=null)portableCancelled.set(true);
        portableLaunchGate=null;portableActive=false;endPortableWindowEvents();
        if(workflowPreparation!=null)workflowPreparation.cancel();
        if(teachingOverlay!=null)teachingOverlay.remove();
        if(workflowRunner!=null)workflowRunner.cancel();
        if(workflowRecorder!=null)workflowRecorder.stop("STOPPED");
        stopRecording(); if (runner != null) runner.cancel();
        if (twoRunner != null) twoRunner.cancel();
        if (deployments != null) deployments.cancel();
        if (pendingCheck != null) { handler.removeCallbacks(pendingCheck); pendingCheck = null; }
    }
    public void checkTwo(TwoStepSkill skill) {
        stopAll(); TwoStepStore store=new TwoStepStore(this); store.checkResult(skill,"CHECKING");
        pendingCheck=() -> {
            pendingCheck=null; String reason;
            try { reason=TwoStepEngine.bindingReason(skill,TwoStepRunner.read(this,skill).scenes); }
            catch(RuntimeException e) { reason="OBSERVATION_ERROR"; }
            store.checkResult(skill,reason);
        };
        handler.postDelayed(pendingCheck,800);
    }
    public void checkSkill(SwitchSkill skill) {
        stopAll();
        SkillStore store = new SkillStore(this);
        store.checkResult(skill, "CHECKING");
        pendingCheck = () -> {
            pendingCheck = null;
            String reason;
            try {
                AccessibilityNodeInfo root = getRootInActiveWindow();
                String pkg = root == null || root.getPackageName() == null ? "" : root.getPackageName().toString();
                List<AccessibilityNodeInfo> nodes = skill.appPackage.equals(pkg)
                        ? root.findAccessibilityNodeInfosByViewId(skill.resourceId) : List.of();
                AccessibilityNodeInfo node = nodes.size() == 1 ? nodes.get(0) : null;
                boolean usable = node != null && node.refresh() && skill.resourceId.equals(node.getViewIdResourceName())
                        && node.getPackageName() != null && skill.appPackage.contentEquals(node.getPackageName())
                        && node.isVisibleToUser() && node.isEnabled() && node.isClickable() && node.isCheckable()
                        && !node.isPassword() && !node.isEditable();
                reason = BindingCheck.reason(skill, new ReplayEngine.Scene(pkg, nodes.size(), usable, usable && node.isChecked()));
            } catch (RuntimeException error) { reason = "OBSERVATION_ERROR"; }
            store.checkResult(skill, reason);
            Log.i(TAG, "binding check=" + reason + " inputs=0");
        };
        handler.postDelayed(pendingCheck, 800);
    }
    public int unattributedChanges() { return trace.unattributedChanges(); }
    public int unsupportedClicks() { return trace.unsupportedClicks(); }
    public String screenshotResult() { return screenshotResult; }

    public void startRecording(String appPackage) {
        startRecording(appPackage,"",TraceBundle.Source.UNKNOWN);
    }

    public void startRecording(String appPackage,String goal,TraceBundle.Source source) {
        if (!ProbePolicy.allowed(appPackage)) throw new IllegalArgumentException("Unsupported app");
        String newId=java.util.UUID.randomUUID().toString();
        // Validate metadata before interrupting an existing recording or changing local state.
        TraceBundle.capture(newId,appPackage,"unknown",goal,source,TraceBundle.End.RECORDING,new DemoTrace());
        stopAll();
        recordingPackage = appPackage;
        traceId=newId;traceGoal=goal;traceSource=source;
        try { traceVersion=Long.toString(getPackageManager().getPackageInfo(appPackage,0).getLongVersionCode()); }
        catch(android.content.pm.PackageManager.NameNotFoundException error) { traceVersion="unknown"; }
        new SkillStore(this).draft(recordingPackage, null);
        new TwoStepStore(this).setDraft(recordingPackage,null,false);
        records.clear();
        trace = new DemoTrace();
        baselineReady = false;
        clickGeneration++;
        handler.removeCallbacks(stableObservation);
        screenshotResult = "Not tested";
        recording = true;
        checkpoint(TraceBundle.End.RECORDING);
        Log.i(TAG, "recording started");
        long thisSession = ++sessionId;
        handler.postDelayed(() -> {
            if (sessionId == thisSession) {
                recording = false;
                trace.abandonPending();
                persistDrafts();
                checkpoint(TraceBundle.End.TIMED_OUT);
                handler.removeCallbacks(stableObservation);
                Log.i(TAG, "recording timed out; count=" + records.size());
            }
        }, 120_000);
    }

    public void stopRecording() {
        boolean wasRecording = recording;
        recording = false;
        sessionId++;
        clickGeneration++;
        trace.abandonPending();
        if (wasRecording) { persistDrafts();checkpoint(TraceBundle.End.STOPPED); }
        handler.removeCallbacks(stableObservation);
        Log.i(TAG, "recording stopped; count=" + records.size());
    }
    public void clearRecords() {
        stopRecording();
        records.clear();
        trace = new DemoTrace();
        baselineReady = false;
    }

    private void checkpoint(TraceBundle.End end) {
        if(traceId==null) return;
        try {
            TraceBundle bundle=TraceBundle.capture(traceId,recordingPackage,traceVersion,traceGoal,traceSource,end,trace);
            traceStorage=new TraceStore(this).save(bundle)?"Saved locally: "+end:"SAVE_FAILED";
        } catch(RuntimeException error) { traceStorage="SAVE_FAILED_INVALID_EVIDENCE"; }
        // Do not log the goal or observed evidence.
    }

    @Override public void onServiceConnected() {
        super.onServiceConnected();
        serviceConnected=false;
        lifecycleState="CONNECTING";lifecycleFailure="";
        if(workflowPreparation!=null)workflowPreparation.cancel();
        if(!workflowRunning()&&(workflowRecorder==null||!workflowRecorder.active())){
            instance=null;
            try{WorkflowSessionRecovery.recover(this);}
            catch(Exception error){lifecycleState="RECOVERY_FAILED";lifecycleFailure=error.getClass().getSimpleName()+":"+error.getMessage();Log.e(TAG,"Workflow recovery unavailable; automation remains disconnected");return;}
        }
        instance = this;
        recording = false;
        runner = new ReplayRunner(this);
        twoRunner = new TwoStepRunner(this);
        deployments = new DeploymentController(this);
        new TwoStepStore(this).clearChecks();
        SkillStore store = new SkillStore(this);
        store.clearChecks();
        try {
            org.json.JSONObject old = new org.json.JSONObject(store.result());
            if ("RUNNING".equals(old.optString("status")))
                store.result(old.put("status", "UNCONFIRMED").put("reason", "SERVICE_RECONNECTED").toString());
        } catch (Exception ignored) { }
        Log.i(TAG, "service connected");
        serviceConnected=true;
        lifecycleState="CONNECTED";
    }

    @Override public boolean onUnbind(android.content.Intent intent) {
        serviceConnected=false;
        lifecycleState="UNBOUND";
        stopAll();
        LearningCapture.invalidate();
        if(instance==this)instance=null;
        return super.onUnbind(intent);
    }

    @Override public void onAccessibilityEvent(AccessibilityEvent event) {
        LearningCapture.event(this,event);
        var launchGate=portableLaunchGate;
        if(launchGate!=null&&event!=null)
            launchGate.metadataEvent(event.getPackageName()==null?null:event.getPackageName().toString(),event.getEventTime(),android.os.SystemClock.elapsedRealtime(),event.getWindowId(),event.getEventType());
        if(portableWindowEventsActive)return; // do not inspect source/text, record or traverse external events
        // Queued events after a temporary scope closes must still obey the original package boundary.
        if(event!=null&&event.getPackageName()!=null&&normalEventPackages!=null
            &&!java.util.Arrays.asList(normalEventPackages).contains(event.getPackageName().toString()))return;
        if(workflowRecorder!=null)workflowRecorder.event(event);
        if (!recording || event == null || event.getPackageName() == null) return;
        AccessibilityNodeInfo root = getRootInActiveWindow();
        if (root == null || root.getPackageName() == null) return;
        AccessibilityNodeInfo source = event.getSource();
        boolean password = source != null && source.isPassword();
        boolean editable = source != null && source.isEditable();
        if (!ProbePolicy.shouldRecord(recording, recordingPackage, event.getPackageName().toString(),
                root.getPackageName().toString(), password, editable)) return;

        String type = AccessibilityEvent.eventTypeToString(event.getEventType());
        String node = source == null ? "source=missing" : describe(source);
        int treeNodes = countNodes(root);
        add(event.getEventTime() + " | " + type + " | " + node + " | treeNodes=" + treeNodes);
        if (event.getEventType() == AccessibilityEvent.TYPE_VIEW_CLICKED) {
            handler.removeCallbacks(stableObservation);
            String id = source == null ? null : source.getViewIdResourceName();
            if (trace.onClick(id, event.getEventTime())) {
                long generation = ++clickGeneration;
                long activeSession = sessionId;
                handler.postDelayed(() -> completeObservedClick(activeSession, generation), 250);
            }
            checkpoint(TraceBundle.End.RECORDING);
        } else if (!trace.hasPending()) {
            handler.removeCallbacks(stableObservation);
            handler.postDelayed(stableObservation, 200);
        }
    }

    private void completeObservedClick(long activeSession, long generation) {
        if (!recording || activeSession != sessionId || generation != clickGeneration) return;
        DemoTrace.Step step = trace.completeClick(currentState());
        if (step != null) Log.i(TAG, "step=" + trace.steps().size() + " outcome=" + step.outcome);
        checkpoint(TraceBundle.End.RECORDING);
    }

    private void observeStableState() {
        if (!recording || trace.hasPending()) return;
        AccessibilityNodeInfo root = getRootInActiveWindow();
        if (root == null || root.getPackageName() == null || !recordingPackage.contentEquals(root.getPackageName())) return;
        Map<String, String> state = snapshot(root);
        if (!baselineReady) {
            trace.setBaseline(state);
            baselineReady = true;
            Log.i(TAG, "baseline ready; fields=" + state.size());
        } else {
            int before = trace.unattributedChanges();
            trace.observeUnattributed(state);
            if (trace.unattributedChanges() > before) Log.i(TAG, "unattributed state change");
        }
        checkpoint(TraceBundle.End.RECORDING);
    }

    private Map<String, String> currentState() {
        AccessibilityNodeInfo root = getRootInActiveWindow();
        if (root == null || root.getPackageName() == null || !recordingPackage.contentEquals(root.getPackageName())) return Map.of();
        return snapshot(root);
    }

    private Map<String, String> snapshot(AccessibilityNodeInfo root) {
        Map<String, String> state = new HashMap<>();
        java.util.HashSet<String> seen = new java.util.HashSet<>();
        ArrayDeque<AccessibilityNodeInfo> queue = new ArrayDeque<>();
        queue.add(root);
        int visited = 0;
        while (!queue.isEmpty() && visited++ < 100) {
            AccessibilityNodeInfo node = queue.removeFirst();
            String id = node.getViewIdResourceName();
            if (id != null && !seen.add(id)) { state.remove(id); }
            else if (id != null && node.getPackageName() != null && recordingPackage.contentEquals(node.getPackageName())
                    && !node.isPassword() && !node.isEditable()) {
                if (node.isCheckable()) state.put(id, "checked=" + node.isChecked());
                else if (node.getRangeInfo() != null)
                    state.put(id, "range=" + node.getRangeInfo().getCurrent());
            }
            for (int i = 0; i < node.getChildCount() && visited + queue.size() < 100; i++) {
                AccessibilityNodeInfo child = node.getChild(i);
                if (child != null) queue.addLast(child);
            }
        }
        return state;
    }

    private String describe(AccessibilityNodeInfo source) {
        Rect bounds = new Rect();
        source.getBoundsInScreen(bounds);
        String resourceId = source.getViewIdResourceName();
        return "class=" + source.getClassName() + " id=" + (resourceId == null ? "-" : resourceId)
                + " bounds=" + bounds.toShortString() + " clickable=" + source.isClickable()
                + " checkable=" + source.isCheckable() + " checked=" + source.isChecked();
    }

    private int countNodes(AccessibilityNodeInfo root) {
        ArrayDeque<AccessibilityNodeInfo> queue = new ArrayDeque<>();
        queue.add(root);
        int count = 0;
        while (!queue.isEmpty() && count < 100) {
            AccessibilityNodeInfo node = queue.removeFirst();
            count++;
            for (int i = 0; i < node.getChildCount() && count + queue.size() < 100; i++) {
                AccessibilityNodeInfo child = node.getChild(i);
                if (child != null) queue.addLast(child);
            }
        }
        return count;
    }

    private void add(String record) {
        if (records.size() == MAX_RECORDS) records.removeFirst();
        records.addLast(record);
        Log.i(TAG, "event accepted; count=" + records.size());
    }

    public void screenshotAfterDelay() {
        Log.i(TAG, "screenshot requested");
        screenshotResult = "Waiting 3 seconds for Lab foreground";
        handler.postDelayed(() -> {
            AccessibilityNodeInfo root = getRootInActiveWindow();
            if (!recording || root == null || !recordingPackage.contentEquals(root.getPackageName())) {
                screenshotResult = "Blocked: recording off or Lab not foreground";
                Log.i(TAG, "screenshot blocked by foreground or recording gate");
                return;
            }
            Log.i(TAG, "screenshot API invoked");
            takeScreenshot(Display.DEFAULT_DISPLAY, getMainExecutor(), new TakeScreenshotCallback() {
                @Override public void onSuccess(ScreenshotResult result) {
                    HardwareBuffer buffer = result.getHardwareBuffer();
                    try {
                        screenshotResult = "Success: " + buffer.getWidth() + "x" + buffer.getHeight()
                                + " (pixels discarded)";
                        Log.i(TAG, "screenshot success");
                    } finally {
                        buffer.close();
                    }
                }

                @Override public void onFailure(int errorCode) {
                    screenshotResult = "Failed: code " + errorCode;
                    Log.i(TAG, "screenshot error code=" + errorCode);
                }
            });
        }, 3000);
    }

    @Override public void onInterrupt() {
        // Accessibility feedback can be interrupted during app switches; only the user or timer stops recording.
    }

    @Override public void onDestroy() {
        serviceConnected=false;
        lifecycleState="DESTROYED";
        if(portableCancelled!=null)portableCancelled.set(true);
        LearningCapture.invalidate();
        if(workflowPreparation!=null)workflowPreparation.cancel();
        if(teachingOverlay!=null)teachingOverlay.remove();
        if(workflowRunner!=null)workflowRunner.cancel();
        if(workflowRecorder!=null)workflowRecorder.stop("INTERRUPTED");
        if(language!=null) language.close();
        if(recording) { trace.abandonPending();checkpoint(TraceBundle.End.INTERRUPTED); }
        recording = false;
        if (deployments != null) deployments.cancel();
        if (runner != null) runner.cancel();
        if (twoRunner != null) twoRunner.cancel();
        handler.removeCallbacksAndMessages(null);
        if(instance==this)instance = null;
        Log.i(TAG, "service destroyed");
        super.onDestroy();
    }
}
