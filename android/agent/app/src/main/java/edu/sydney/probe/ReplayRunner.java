package edu.sydney.probe;

import android.accessibilityservice.AccessibilityService;
import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;
import android.util.Log;
import android.view.accessibility.AccessibilityNodeInfo;
import org.json.JSONObject;
import java.util.List;

public final class ReplayRunner {
    private final AccessibilityService service;
    private final SkillStore store;
    private final Handler handler = new Handler(Looper.getMainLooper());
    private ReplayEngine engine;
    private String runId;
    private int inputAttempts;
    private final Runnable tick = this::observe;
    public ReplayRunner(AccessibilityService service) { this.service = service; store = new SkillStore(service); }
    public boolean running() { return engine != null && "RUNNING".equals(engine.status); }
    public void start(SwitchSkill skill, boolean desired) {
        cancel();
        runId = java.util.UUID.randomUUID().toString();
        inputAttempts = 0;
        engine = new ReplayEngine(skill, desired, SystemClock.elapsedRealtime(), 3500);
        publish();
        handler.postDelayed(tick, 800);
    }
    public void cancel() {
        handler.removeCallbacks(tick);
        if (running()) { engine.cancel(SystemClock.elapsedRealtime()); publish(); }
    }
    private void observe() {
        try { observeCurrent(); }
        catch (RuntimeException error) {
            if (running()) { engine.observationFailed(SystemClock.elapsedRealtime()); publish(); }
            Log.e("DemoReplay", "observation failed", error);
        }
    }
    private void observeCurrent() {
        if (!running()) return;
        AccessibilityNodeInfo root = service.getRootInActiveWindow();
        String pkg = root == null || root.getPackageName() == null ? "" : root.getPackageName().toString();
        List<AccessibilityNodeInfo> nodes = engine.skill.appPackage.equals(pkg)
                ? root.findAccessibilityNodeInfosByViewId(engine.skill.resourceId) : List.of();
        AccessibilityNodeInfo node = nodes.size() == 1 ? nodes.get(0) : null;
        boolean usable = node != null && node.refresh() && engine.skill.resourceId.equals(node.getViewIdResourceName())
                && node.getPackageName() != null && engine.skill.appPackage.contentEquals(node.getPackageName())
                && node.isVisibleToUser() && node.isEnabled() && node.isCheckable() && node.isClickable()
                && !node.isPassword() && !node.isEditable();
        ReplayEngine.Action action = engine.observe(new ReplayEngine.Scene(pkg, nodes.size(), usable,
                usable && node.isChecked()), SystemClock.elapsedRealtime());
        if (action == ReplayEngine.Action.CLICK) {
            AccessibilityNodeInfo freshRoot = service.getRootInActiveWindow();
            boolean sameApp = freshRoot != null && freshRoot.getPackageName() != null
                    && engine.skill.appPackage.contentEquals(freshRoot.getPackageName());
            if (SystemClock.elapsedRealtime() >= engine.deadline) engine.observe(null, SystemClock.elapsedRealtime());
            else if (!sameApp)
                engine.inputRejected(SystemClock.elapsedRealtime());
            else {
                inputAttempts++;
                publish();
                if (!node.performAction(AccessibilityNodeInfo.ACTION_CLICK)) engine.inputRejected(SystemClock.elapsedRealtime());
            }
        }
        if (running()) handler.postDelayed(tick, 100);
        else publish();
    }
    private void publish() {
        try {
            JSONObject value = new JSONObject().put("runId", runId).put("status", engine.status)
                    .put("reason", engine.reason).put("package", engine.skill.appPackage)
                    .put("target", engine.skill.resourceId).put("desired", engine.desired)
                    .put("inputs", inputAttempts).put("observations", engine.observations)
                    .put("initialObserved", engine.initialObserved == null ? JSONObject.NULL : engine.initialObserved)
                    .put("elapsedMs", (running() ? SystemClock.elapsedRealtime() : engine.finishedAt) - engine.startedAt);
            store.result(value.toString());
            Log.i("DemoReplay", value.toString());
        } catch (Exception e) { Log.e("DemoReplay", "result serialization failed", e); }
    }
}
