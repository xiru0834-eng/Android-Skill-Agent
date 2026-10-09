package edu.sydney.probe;

import android.graphics.Rect;
import android.os.Process;
import android.view.accessibility.AccessibilityNodeInfo;
import android.view.accessibility.AccessibilityWindowInfo;
import java.io.File;
import java.util.List;
import java.util.TreeSet;
import org.json.*;

/** Normal capture adapter. Returns inert facts, never a Resolved or input permit. */
final class LearningIdentityReference {
    static JSONObject collect(ProbeService service,AccessibilityNodeInfo root,JSONObject tree)throws Exception {
        JSONObject out=new JSONObject().put("schema_version","1.0").put("producer","LearningIdentityReference.v1")
            .put("source_mode","REFERENCE_ASSISTED").put("execution_authority",false)
            .put("process_id",Process.myPid()).put("status","UNKNOWN").put("links",new JSONArray())
            .put("limitations",new JSONArray().put("PRECONFIGURED_LOCALLY_REVIEWED_REFERENCE")
                .put("EXPERIMENT_APP_NO_ACCOUNT_OR_SITE_CONTEXT").put("CAPTURE_TIME_FACT_NOT_EXECUTION_PERMISSION"));
        if(!PortableSkillCodec.PKG.contentEquals(root.getPackageName()))return out.put("reason","REFERENCE_NOT_APPLICABLE");
        List<AccessibilityWindowInfo> windows=null;
        try {
            var before=reference(service);
            windows=service.getWindows();var frame=PortableWindowGuard.frame(root,windows);
            if(!PortableSkillCodec.PAGE.equals(frame.page)||!tree.getBoolean("complete"))
                throw new IllegalStateException("REFERENCE_CONTEXT_UNCONFIRMED");
            var pkg=new PortableSkillStore(service).approved();JSONArray links=new JSONArray();boolean confirmed=true;
            for(String key:new TreeSet<>(pkg.binding.targets.keySet())) {
                var r=AccessibilityBindingResolver.resolve(key,pkg.binding,root,frame.page);
                JSONObject link=new JSONObject().put("semantic_key",key).put("status",r.status.name()).put("reason",r.reason);
                if(r.resolved!=null)try {
                    var node=r.resolved.node;Rect b=new Rect();node.getBoundsInScreen(b);
                    JSONArray matches=new JSONArray();JSONArray nodes=tree.getJSONArray("nodes");
                    for(int i=0;i<nodes.length();i++) {
                        JSONObject row=nodes.getJSONObject(i);JSONArray old=row.getJSONArray("bounds");
                        if(same(row.opt("resource_id"),node.getViewIdResourceName())&&same(row.opt("class_name"),node.getClassName())
                            &&same(row.opt("text"),node.getText())&&same(row.opt("content_description"),node.getContentDescription())
                            &&old.getInt(0)==b.left&&old.getInt(1)==b.top&&old.getInt(2)==b.right&&old.getInt(3)==b.bottom
                            &&row.getBoolean("visible")==node.isVisibleToUser()&&row.getBoolean("enabled")==node.isEnabled()
                            &&row.getBoolean("checked")==node.isChecked()&&rangeMatches(row,node))matches.put(row.getString("node_local_id"));
                    }
                    if(matches.length()!=1||!node.isVisibleToUser()||!node.isEnabled()||node.isEditable()||node.isPassword()) {
                        link.put("status",matches.length()>1?"AMBIGUOUS":"NOT_FOUND").put("reason","CURRENT_TREE_ASSOCIATION_NOT_UNIQUE");
                    } else {
                        int dot=key.lastIndexOf('.');link.put("entity_id",key.substring(0,dot)).put("property",key.substring(dot+1))
                            .put("node_local_id",matches.getString(0)).put("strategy",r.resolved.strategy)
                            .put("matching_conditions","CANONICAL_RESOLVER_PAGE_ROLE_LOCAL_SCOPE_UNIQUE_AND_SAME_TREE_NODE");
                    }
                } finally {r.resolved.node.recycle();}
                if(!"RESOLVED".equals(link.getString("status")))confirmed=false;
                links.put(link);
            }
            var after=reference(service);
            if(!before.toString().equals(after.toString()))throw new IllegalStateException("REFERENCE_REVISION_CHANGED");
            return out.put("reference",before).put("page",frame.page).put("links",links)
                .put("status",confirmed?"CONFIRMED":"UNKNOWN").put("reason",confirmed?"":"UNRESOLVED_REFERENCE_TARGET");
        } catch(Exception error) {
            return out.put("status","UNKNOWN").put("links",new JSONArray()).put("reason",error.getMessage()==null?"REFERENCE_READ_ERROR":error.getMessage());
        } finally {if(windows!=null)for(var w:windows)w.recycle();}
    }
    private static JSONObject reference(ProbeService service)throws Exception {
        var pkg=new PortableSkillStore(service).approved();
        File data=new File(service.getFilesDir(),"portable-approved.json");
        File approval=new File(service.getApplicationInfo().dataDir,"shared_prefs/portable_approval.xml");
        return new JSONObject().put("content_sha256",pkg.hash)
            .put("revision",pkg.hash+":"+data.lastModified()+":"+approval.lastModified())
            .put("approval_provenance","CURRENT_LOCAL_PORTABLE_SKILL_STORE_HASH_CHECK")
            .put("app_package",pkg.binding.packageName).put("app_version",pkg.appVersion)
            .put("app_build",service.getPackageManager().getPackageInfo(pkg.binding.packageName,0).getLongVersionCode())
            .put("scope","parameter-room-u0.EXPERIMENT_APP");
    }
    private static boolean same(Object a,CharSequence b) {
        return (a==null||a==JSONObject.NULL?"":a.toString()).equals(b==null?"":b.toString());
    }
    private static boolean rangeMatches(JSONObject row,AccessibilityNodeInfo node)throws JSONException {
        JSONObject r=row.optJSONObject("range");var n=node.getRangeInfo();
        return r==null?n==null:n!=null&&r.getDouble("min")==n.getMin()&&r.getDouble("max")==n.getMax()&&r.getDouble("value")==n.getCurrent();
    }
}
