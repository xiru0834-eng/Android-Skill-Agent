package edu.sydney.probe;

import android.accessibilityservice.AccessibilityService;
import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;
import android.view.accessibility.AccessibilityNodeInfo;
import org.json.JSONArray;
import org.json.JSONObject;
import java.util.ArrayList;
import java.util.List;

public final class TwoStepRunner {
    private final AccessibilityService service;
    private final Handler handler=new Handler(Looper.getMainLooper());
    private final SkillStore results;
    private TwoStepEngine engine;
    private String runId;
    private int attempts;
    private DeploymentSkill deployment;
    private final Runnable tick=this::observe;
    public TwoStepRunner(AccessibilityService service) { this.service=service;results=new SkillStore(service); }
    public void start(TwoStepSkill skill,List<Boolean> desired) {
        start(skill,desired,null);
    }
    public void startDeployment(DeploymentSkill skill,List<Boolean> desired) { start(skill.boundSkill(),desired,skill); }
    private void start(TwoStepSkill skill,List<Boolean> desired,DeploymentSkill provenance) {
        cancel(); deployment=provenance;engine=new TwoStepEngine(skill,desired,SystemClock.elapsedRealtime(),3500);
        runId=java.util.UUID.randomUUID().toString();attempts=0;publish();handler.postDelayed(tick,800);
    }
    public void cancel() { handler.removeCallbacks(tick);if(engine!=null && engine.running()) { engine.cancel(SystemClock.elapsedRealtime());publish(); } }
    public static final class Observation {
        public final List<ReplayEngine.Scene> scenes=new ArrayList<>();
        final List<AccessibilityNodeInfo> nodes=new ArrayList<>();
    }
    public static Observation read(AccessibilityService service,TwoStepSkill skill) {
        Observation out=new Observation(); AccessibilityNodeInfo root=service.getRootInActiveWindow();
        String pkg=root==null || root.getPackageName()==null?"":root.getPackageName().toString();
        for(SwitchSkill step:skill.steps) {
            List<AccessibilityNodeInfo> matches=step.appPackage.equals(pkg)?root.findAccessibilityNodeInfosByViewId(step.resourceId):List.of();
            AccessibilityNodeInfo node=matches.size()==1?matches.get(0):null;
            boolean usable=node!=null && node.refresh() && step.resourceId.equals(node.getViewIdResourceName())
                    && node.getPackageName()!=null && step.appPackage.contentEquals(node.getPackageName())
                    && node.isVisibleToUser() && node.isEnabled() && node.isCheckable() && node.isClickable()
                    && !node.isPassword() && !node.isEditable();
            out.nodes.add(node);out.scenes.add(new ReplayEngine.Scene(pkg,matches.size(),usable,usable && node.isChecked()));
        }
        return out;
    }
    private void observe() {
        if(engine==null || !engine.running()) return;
        try {
            Observation observed=read(service,engine.skill);
            int action=engine.observe(observed.scenes,SystemClock.elapsedRealtime());
            if(action>=0) {
                // Re-read both bindings and all established obligations immediately before input.
                Observation fresh=read(service,engine.skill);
                if(SystemClock.elapsedRealtime()>=engine.deadline) engine.observe(null,SystemClock.elapsedRealtime());
                else if(!"READY".equals(TwoStepEngine.bindingReason(engine.skill,fresh.scenes))) engine.inputRejected(SystemClock.elapsedRealtime());
                else if(fresh.scenes.get(action).checked==engine.desired.get(action)) {
                    // An external change already reached the goal: do not toggle it away.
                } else {
                    boolean stable=true;
                    for(int i=0;i<engine.completed;i++) stable &= fresh.scenes.get(i).checked==engine.desired.get(i);
                    if(!stable) engine.observe(fresh.scenes,SystemClock.elapsedRealtime());
                    else {
                        attempts++;publish();
                        if(!fresh.nodes.get(action).performAction(AccessibilityNodeInfo.ACTION_CLICK)) engine.inputRejected(SystemClock.elapsedRealtime());
                    }
                }
            }
        } catch(RuntimeException error) { engine.observationFailed(SystemClock.elapsedRealtime()); }
        if(engine.running()) handler.postDelayed(tick,100);else publish();
    }
    private void publish() {
        try {
            JSONArray targets=new JSONArray();for(SwitchSkill s:engine.skill.steps) targets.put(s.resourceId);
            JSONObject report=new JSONObject().put("runId",runId).put("kind",deployment==null?"TWO_STEP":"DEPLOYMENT").put("status",engine.status)
                    .put("reason",engine.reason).put("package",engine.skill.appPackage).put("targets",targets)
                    .put("desired",new JSONArray(engine.desired)).put("inputs",attempts).put("plannedInputs",engine.inputs)
                    .put("completedSteps",engine.completed).put("observations",engine.observations)
                    .put("elapsedMs",(engine.running()?SystemClock.elapsedRealtime():engine.finishedAt)-engine.startedAt);
            if(deployment!=null) report.put("workflowId",deployment.workflowId).put("bindingId",deployment.bindingId);
            results.result(report.toString());
        } catch(Exception e) { throw new IllegalStateException("Cannot persist result",e); }
    }
}
