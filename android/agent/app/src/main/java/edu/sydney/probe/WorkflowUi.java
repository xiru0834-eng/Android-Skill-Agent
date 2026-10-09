package edu.sydney.probe;

import android.view.accessibility.AccessibilityNodeInfo;
import java.util.*;
import java.util.regex.*;
import org.json.*;

/** Public accessibility only. No fixture private data or test oracle access. */
final class WorkflowUi {
    static final String PKG=TransferLabSelectors.PACKAGE;
    static final class WrongApp extends IllegalStateException {
        final String rootKind;final int windowId;
        WrongApp(AccessibilityNodeInfo root){
            super("WRONG_APP");
            rootKind=root==null?"NONE":("edu.sydney.probe".equals(String.valueOf(root.getPackageName()))?"CONTROLLER":"OTHER");
            windowId=root==null?-1:root.getWindowId();
        }
    }
    static final Pattern SUMMARY=Pattern.compile("Saved lamp: (ON|OFF) · (20|40|60|80|100)%\\nSaved fan: (ON|OFF) · speed ([123])");
    static AccessibilityNodeInfo root(ProbeService service) {
        AccessibilityNodeInfo r=service.getRootInActiveWindow();
        if(r==null||!PKG.equals(String.valueOf(r.getPackageName())))throw new WrongApp(r);
        return r;
    }
    // Off-screen nodes may be observed, but never clicked without a fresh visibility check.
    static AccessibilityNodeInfo observedNode(ProbeService service,String id) {
        return observedNode(root(service),id);
    }
    private static AccessibilityNodeInfo observedNode(AccessibilityNodeInfo root,String id) {
        // Dynamic observation markers remain ID-only. Action targets use the environment resolver.
        if(id.startsWith("wfOpen")||id.matches("wf(Lamp|Fan)(Power|Value[0-9]+|Save|Cancel|Back)")){
            return resolved(root,id).node;
        }
        return rawNode(root,id);
    }
    private static AccessibilityNodeInfo rawNode(AccessibilityNodeInfo root,String id) {
        List<AccessibilityNodeInfo> nodes=root.findAccessibilityNodeInfosByViewId(PKG+":id/"+id);
        if(nodes.size()!=1)throw new IllegalStateException(nodes.isEmpty()?"MISSING:"+id:"AMBIGUOUS:"+id);
        AccessibilityNodeInfo n=nodes.get(0);
        if(!n.refresh())throw new IllegalStateException("STALE:"+id);
        if(n.isPassword()||n.isEditable()||!PKG.contentEquals(n.getPackageName()))throw new IllegalStateException("UNUSABLE:"+id);
        return n;
    }
    private static AccessibilityBindingResolver.Resolved resolved(AccessibilityNodeInfo root,String id){
        try{return AccessibilityBindingResolver.resolve(root,TransferLabSelectors.target(id),page(root));}
        catch(EnvironmentBinding.Failure failure){
            throw new IllegalStateException(WorkflowResolutionReason.translate(failure.getMessage(),id),failure);
        }
    }
    static AccessibilityBindingResolver.Resolved resolveNode(ProbeService service,String id){
        AccessibilityNodeInfo r=root(service);
        AccessibilityBindingResolver.Resolved result;
        try{result=AccessibilityBindingResolver.resolveFresh(source(service),TransferLabSelectors.target(id),page(r),r.getWindowId());}
        catch(EnvironmentBinding.Failure failure){throw new IllegalStateException(WorkflowResolutionReason.translate(failure.getMessage(),id),failure);}
        if(!result.node.isVisibleToUser())throw new IllegalStateException("UNUSABLE:"+id);
        AccessibilityNodeInfo current=root(service);
        if(current.getWindowId()!=r.getWindowId()||!page(current).equals(result.page))throw new IllegalStateException("PAGE_CHANGED");
        return result;
    }
    static AccessibilityBindingResolver.RootSource source(ProbeService service){
        return ()->{AccessibilityNodeInfo r=root(service);return new AccessibilityBindingResolver.Frame(r,page(r));};
    }
    static boolean click(ProbeService service,AccessibilityBindingResolver.Resolved permit,long deadline){
        try{return AccessibilityBindingResolver.click(source(service),permit,deadline);}
        catch(EnvironmentBinding.Failure failure){throw new IllegalStateException(WorkflowResolutionReason.translate(failure.getMessage(),permit.target.key),failure);}
    }
    static AccessibilityNodeInfo node(ProbeService service,String id) {
        return resolveNode(service,id).node;
    }
    static String text(ProbeService service,String id) {CharSequence t=observedNode(service,id).getText();return t==null?"":t.toString();}
    private static String text(AccessibilityNodeInfo root,String id){CharSequence t=observedNode(root,id).getText();return t==null?"":t.toString();}
    static String page(ProbeService s) {
        return page(root(s));
    }
    private static String page(AccessibilityNodeInfo root){
        String p=text(root,"wfPage");
        for(String name:List.of("overview","single","lamp","fan"))if(p.equals(name+" | bedroom"))return name;
        throw new IllegalStateException("UNSUPPORTED_PAGE");
    }
    static JSONArray saved(ProbeService s) {
        return saved(root(s));
    }
    private static JSONArray saved(AccessibilityNodeInfo root){
        Matcher m=SUMMARY.matcher(text(root,"wfSummary"));if(!m.matches())throw new IllegalStateException("INVALID_SUMMARY");
        return new JSONArray().put(m.group(1).equals("ON")?1:0).put(Integer.parseInt(m.group(2))).put(m.group(3).equals("ON")?1:0).put(Integer.parseInt(m.group(4)));
    }
    static JSONObject snapshot(ProbeService s) {
        try {
            AccessibilityNodeInfo root=root(s);
            if(!text(root,"wfReady").startsWith("Ready /"))throw new IllegalStateException("NOT_READY");
            String p=page(root);JSONObject values=new JSONObject();boolean dirty=false;
            if(p.equals("overview")||p.equals("single")) {
                String overall=text(root,"wfOverallDirty");
                if(!overall.startsWith("Saved /")&&!overall.startsWith("Unsaved changes /"))throw new IllegalStateException("INVALID_DIRTY");
                dirty=overall.startsWith("Unsaved");
            }
            for(String group:List.of("lamp","fan"))if(p.equals("single")||p.equals(group)) {
                String prefix=group.equals("lamp")?"wfLamp":"wfFan";
                AccessibilityNodeInfo power=observedNode(root,prefix+"Power");if(!power.isCheckable())throw new IllegalStateException("NOT_CHECKABLE");
                values.put(prefix+"Power",power.isChecked());int selected=0;
                for(int v:group.equals("lamp")?new int[]{20,40,60,80,100}:new int[]{1,2,3}) {
                    AccessibilityNodeInfo n=observedNode(root,prefix+"Value"+v);if(!n.isCheckable())throw new IllegalStateException("NOT_CHECKABLE");
                    values.put(prefix+"Value"+v,n.isChecked());if(n.isChecked())selected++;
                }
                if(selected!=1)throw new IllegalStateException("INVALID_SELECTION");
                String d=text(root,prefix+"Dirty");if(!d.startsWith("Saved /")&&!d.startsWith("Unsaved changes /"))throw new IllegalStateException("INVALID_DIRTY");
                if(!p.equals("single"))dirty=d.startsWith("Unsaved");
            }
            if(!p.equals(page(root)))throw new IllegalStateException("PAGE_CHANGED");
            return new JSONObject().put("page",p).put("values",values).put("saved",p.equals("overview")||p.equals("single")?saved(root):new JSONArray()).put("dirty",dirty);
        }catch(JSONException e){throw new IllegalStateException("SNAPSHOT_JSON");}
    }
    static Map<String,String> labels(ProbeService s) {
        Map<String,String> labels=new HashMap<>();ArrayDeque<AccessibilityNodeInfo> q=new ArrayDeque<>();q.add(root(s));int count=0;
        while(!q.isEmpty()&&count++<100) {
            AccessibilityNodeInfo n=q.removeFirst();String id=n.getViewIdResourceName();
            if(id!=null&&id.startsWith(PKG+":id/wf")&&n.isClickable()&&!n.isEditable()&&!n.isPassword())
                labels.put(id.substring((PKG+":id/").length()),n.getText()==null?"":n.getText().toString());
            for(int i=0;i<n.getChildCount()&&q.size()<100;i++){AccessibilityNodeInfo c=n.getChild(i);if(c!=null)q.add(c);}
        }
        return labels;
    }

    /** Same public-tree observation for both single- and multi-page recording. */
    static JSONObject recordingSnapshot(ProbeService s) {
        return snapshot(s);
    }
}
