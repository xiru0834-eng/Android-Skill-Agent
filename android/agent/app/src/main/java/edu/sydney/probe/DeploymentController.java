package edu.sydney.probe;

import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;
import android.view.accessibility.AccessibilityNodeInfo;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.List;

/** Only read-only discovery/preflight; input remains in the reviewed execution path. */
public final class DeploymentController {
    public static final class Catalog {
        public final String pkg,reason;
        public final long capturedAt;
        public final List<BindingCatalog.Node> nodes;
        Catalog(String pkg,String reason,List<BindingCatalog.Node> nodes) {
            this.pkg=pkg;this.reason=reason;this.nodes=nodes;capturedAt=SystemClock.elapsedRealtime();
        }
    }
    private final ProbeService service;
    private final Handler handler=new Handler(Looper.getMainLooper());
    private Catalog catalog;
    public DeploymentController(ProbeService service) { this.service=service;new DeploymentStore(service).clearCheck(); }
    public Catalog catalog() { return catalog; }
    public void cancel() { handler.removeCallbacksAndMessages(null); }
    public void scan(String pkg) {
        if(!ProbePolicy.allowed(pkg)) throw new IllegalArgumentException("App not allowed");
        cancel();catalog=new Catalog(pkg,"SCANNING",List.of());
        handler.postDelayed(()-> { try { catalog=read(pkg); } catch(RuntimeException e) { catalog=new Catalog(pkg,"OBSERVATION_ERROR",List.of()); } },800);
    }
    public void check(DeploymentSkill skill) {
        cancel();DeploymentStore store=new DeploymentStore(service);store.checkResult(skill,"CHECKING");
        handler.postDelayed(()-> {
            String reason;
            try { reason=TwoStepEngine.bindingReason(skill.boundSkill(),TwoStepRunner.read(service,skill.boundSkill()).scenes); }
            catch(RuntimeException e) { reason="OBSERVATION_ERROR"; }
            store.checkResult(skill,reason);
        },800);
    }
    private Catalog read(String pkg) {
        AccessibilityNodeInfo root=service.getRootInActiveWindow();
        if(root==null || !pkg.contentEquals(root.getPackageName())) return new Catalog(pkg,"WRONG_APP",List.of());
        ArrayDeque<AccessibilityNodeInfo> queue=new ArrayDeque<>();queue.add(root);int count=0;
        List<BindingCatalog.Node> nodes=new ArrayList<>();
        while(!queue.isEmpty()) {
            if(++count>200) return new Catalog(pkg,"TREE_LIMIT",List.of());
            AccessibilityNodeInfo n=queue.removeFirst();String id=n.getViewIdResourceName();
            boolean usable=n.refresh() && pkg.contentEquals(n.getPackageName()) && n.isVisibleToUser() && n.isEnabled()
                    && n.isClickable() && n.isCheckable() && !n.isPassword() && !n.isEditable();
            String label="";
            if(usable) { CharSequence text=n.getText()!=null?n.getText():n.getContentDescription();
                label=text==null?"Unlabelled control":text.toString().replaceAll("[\\p{Cntrl}\\p{Cf}]", " ");if(label.length()>64) label=label.substring(0,64); }
            nodes.add(new BindingCatalog.Node(id,label,usable));
            if(n.getChildCount()+queue.size()+count>200) return new Catalog(pkg,"TREE_LIMIT",List.of());
            for(int i=0;i<n.getChildCount();i++) { AccessibilityNodeInfo child=n.getChild(i);if(child!=null) queue.add(child); }
        }
        AccessibilityNodeInfo current=service.getRootInActiveWindow();
        if(current==null || !pkg.contentEquals(current.getPackageName())) return new Catalog(pkg,"WRONG_APP",List.of());
        List<BindingCatalog.Node> candidates=BindingCatalog.select(pkg,nodes);
        return new Catalog(pkg,candidates.size()>=2?"READY":"INSUFFICIENT_TARGETS",candidates);
    }
}
