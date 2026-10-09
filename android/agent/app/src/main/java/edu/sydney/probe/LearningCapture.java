package edu.sydney.probe;

import android.graphics.Rect;
import android.os.Build;
import android.os.SystemClock;
import android.view.accessibility.AccessibilityEvent;
import android.view.accessibility.AccessibilityNodeInfo;
import android.view.accessibility.AccessibilityWindowInfo;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.regex.Pattern;
import org.json.*;

/** Explicit opt-in learning scope, real Tree A/B and passive events in the existing service.
 * SDK signatures: developer.android.com/reference/android/accessibilityservice/AccessibilityService
 * and /android/view/accessibility/AccessibilityNodeInfo. No cached Node survives a request.
 */
final class LearningCapture {
    static final String PROCESS_SESSION=UUID.randomUUID().toString();
    static final int MAX_NODES=2048,MAX_DEPTH=64,TEXT_LIMIT=256;
    static final long CAPTURE_MS=2000,PAIR_MS=250;
    private static final Pattern SECRET=Pattern.compile("(?i)\\bsk-[A-Za-z0-9_-]{12,}");
    private static final Pattern BEARER=Pattern.compile("(?i)\\bBearer\\s+\\S+");
    private static final Pattern CONTACT=Pattern.compile("\\b[\\w.+-]+@[\\w.-]+\\.[A-Za-z]{2,}\\b");
    private static final Pattern PHONE=Pattern.compile("(?<!\\d)(?:\\+?86[- ]?)?1[3-9]\\d{9}(?!\\d)");
    private static final Pattern PATH=Pattern.compile("(?i)(?:[A-Z]:[\\\\/]|file://|\\\\\\\\)[^\\s\"<>]+");
    private static LearningScope scope;
    private static JSONObject lastObservation;
    private static JSONObject captureFailure;
    private static final ArrayList<JSONObject> events=new ArrayList<>();
    private static long eventSeq;private static boolean eventsTruncated;
    static void invalidate(){if(scope!=null)scope.cancel();lastObservation=null;}
    static void start(String id,String pkg,long now){
        if(scope!=null){try{scope.require(scope.id,now);throw new IllegalStateException("SCOPE_ALREADY_ACTIVE");}
            catch(IllegalStateException e){if("SCOPE_ALREADY_ACTIVE".equals(e.getMessage()))throw e;}}
        scope=new LearningScope(id,pkg,now);lastObservation=null;captureFailure=null;events.clear();eventsTruncated=false;eventSeq=0;
    }
    static JSONObject counters()throws JSONException{return new JSONObject().put("actions",scope==null?0:scope.actions)
        .put("captures",scope==null?0:scope.captures).put("events_truncated",eventsTruncated);}
    static void require(String id){if(scope==null)throw new IllegalStateException("SCOPE_NOT_STARTED");scope.require(id,SystemClock.elapsedRealtime());}
    static JSONObject finish(String id)throws JSONException{
        require(id);JSONObject out=eventCopy();scope.cancel();lastObservation=null;return out;
    }
    static JSONObject cancel(String id)throws JSONException{
        if(scope==null||!scope.id.equals(id))throw new IllegalStateException("SCOPE_MISMATCH");
        scope.cancel();lastObservation=null;return eventCopy();
    }
    static JSONObject eventCopy()throws JSONException{
        JSONArray out=new JSONArray();for(JSONObject e:events)out.put(new JSONObject(e.toString()));
        return new JSONObject().put("events",out).put("events_truncated",eventsTruncated).put("sequence",eventSeq);
    }
    static void event(ProbeService service,AccessibilityEvent event){
        if(scope==null||event==null)return;
        try{
            scope.require(scope.id,SystemClock.elapsedRealtime());
            String pkg=event.getPackageName()==null?null:event.getPackageName().toString();
            if(!scope.pkg.equals(pkg)){
                if(event.getEventType()==AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED)invalidate();
                return; // No external App text/source is collected.
            }
            if(events.size()>=LearningScope.MAX_EVENTS){eventsTruncated=true;return;}
            AccessibilityNodeInfo node=null;
            try{
                node=event.getSource();String rid=node==null?null:node.getViewIdResourceName();
                if(node!=null&&!scope.pkg.contentEquals(node.getPackageName()==null?"":node.getPackageName()))return;
                events.add(new JSONObject().put("event_id",PROCESS_SESSION+":"+(++eventSeq))
                    .put("event_type",event.getEventType()).put("event_uptime_ms",event.getEventTime())
                    .put("received_uptime_ms",SystemClock.uptimeMillis()).put("received_elapsed_ms",SystemClock.elapsedRealtime())
                    .put("window_id",event.getWindowId()).put("package",pkg).put("resource_id",nullable(rid))
                    .put("actor","UNKNOWN").put("source","ANDROID_ACCESSIBILITY_EVENT"));
            }finally{if(node!=null)node.recycle();}
        }catch(Exception ignored){invalidate();}
    }
    static JSONObject capture(ProbeService service,String scopeId,String observationId)throws Exception{
        require(scopeId);scope.capture(scopeId,SystemClock.elapsedRealtime());
        lastObservation=null;captureFailure=null; // A failed new capture cannot leave an old input reference usable.
        long begin=SystemClock.elapsedRealtime(),deadline=begin+CAPTURE_MS;
        JSONArray attempts=new JSONArray();JSONObject result=null;
        for(int n=1;n<=2;n++){
            JSONObject attempt=new JSONObject().put("attempt_id",observationId+":"+n);
            attempts.put(attempt);
            long attemptStart=SystemClock.elapsedRealtime();attempt.put("started_elapsed_ms",attemptStart);
            try{
            long a0=SystemClock.uptimeMillis();JSONObject a=snapshot(service,scope.pkg);long a1=SystemClock.uptimeMillis();
            long b0=SystemClock.uptimeMillis();JSONObject b=snapshot(service,scope.pkg);long b1=SystemClock.uptimeMillis();
            attempt.put("tree_a_start_uptime_ms",a0).put("tree_a_end_uptime_ms",a1).put("tree_b_start_uptime_ms",b0)
                .put("tree_b_end_uptime_ms",b1).put("tree_a",a).put("tree_b",b);
            boolean window=a.getInt("window_id")==b.getInt("window_id");
            boolean tree=a.getJSONObject("tree").toString().equals(b.getJSONObject("tree").toString())
                &&a.getJSONObject("identity_reference").toString().equals(b.getJSONObject("identity_reference").toString());
            boolean pair=b1>=a0&&b1-a0<=PAIR_MS&&SystemClock.elapsedRealtime()<=deadline;
            attempt.put("status",window&&tree&&pair?"VALID_TREE_ONLY":"OBSERVATION_INCONSISTENT");
            attempt.put("window_match",window).put("tree_match",tree).put("pair_span_ms",b1-a0);
            if(window&&tree&&pair){result=new JSONObject().put("kind","NativePageObservation").put("schema_version","1.0")
                .put("observation_id",observationId).put("channel","REAL_ANDROID_BOUND_SERVICE").put("process_session",PROCESS_SESSION)
                .put("scope_id",scope.id).put("app_package",scope.pkg).put("captured_elapsed_ms",SystemClock.elapsedRealtime())
                .put("captured_uptime_ms",b1).put("capture_started_elapsed_ms",begin).put("window_id",b.getInt("window_id"))
                .put("display_id",b.getInt("display_id")).put("tree",b.getJSONObject("tree"))
                .put("app_build",service.getPackageManager().getPackageInfo(scope.pkg,0).getLongVersionCode())
                .put("device_context",AndroidDeviceContext.capture(service,scope.pkg)).put("attempts",attempts)
                .put("status","VALID_TREE_ONLY").put("screenshot",JSONObject.NULL).put("screenshot_status","NOT_REQUESTED")
                .put("pairing_level","WINDOW_TIME_CHECKED").put("visual_content_check","NOT_EVALUATED")
                .put("limitations",new JSONArray().put("NOT_ATOMIC_FRAME").put("NO_VISUAL_CONTENT_CHECK"));
                JSONObject association=new JSONObject(b.getJSONObject("identity_reference").toString())
                    .put("association_id",UUID.randomUUID().toString()).put("observation_id",observationId)
                    .put("process_session",PROCESS_SESSION).put("window_id",b.getInt("window_id"))
                    .put("display_id",b.getInt("display_id")).put("captured_elapsed_ms",result.getLong("captured_elapsed_ms"));
                result.put("identity_association",association);
                if(SystemClock.elapsedRealtime()>deadline)throw new IllegalStateException("CAPTURE_TIMEOUT");break;}
            if(SystemClock.elapsedRealtime()>=deadline)break;
            }catch(Exception error){
                String code=error instanceof NullPointerException?"TREE_API_ERROR":error.getMessage();
                attempt.put("status","CAPTURE_ATTEMPT_FAILED").put("error_code",code==null?"TREE_API_ERROR":code)
                    .put("error_class",error.getClass().getSimpleName()).put("finished_elapsed_ms",SystemClock.elapsedRealtime());
                boolean transientRead=error instanceof NullPointerException||"ROOT_UNAVAILABLE".equals(code)||"WINDOW_MISMATCH".equals(code)
                    ||"WINDOW_UNAVAILABLE".equals(code)||"TREE_API_ERROR".equals(code);
                if(!transientRead||n==2||SystemClock.elapsedRealtime()>=deadline){
                    captureFailure=new JSONObject().put("observation_id",observationId).put("attempts",attempts)
                        .put("capture_started_elapsed_ms",begin).put("finished_elapsed_ms",SystemClock.elapsedRealtime());
                    throw new IllegalStateException(code==null?"TREE_API_ERROR":code,error);
                }
                SystemClock.sleep(Math.min(50,Math.max(0,deadline-SystemClock.elapsedRealtime())));
                require(scopeId);
            }
        }
        if(result==null){lastObservation=null;captureFailure=new JSONObject().put("observation_id",observationId)
            .put("attempts",attempts).put("capture_started_elapsed_ms",begin).put("finished_elapsed_ms",SystemClock.elapsedRealtime());
            throw new IllegalStateException("OBSERVATION_INCONSISTENT");}
        require(scopeId);lastObservation=result;scope.observed(observationId,SystemClock.elapsedRealtime());return result;
    }
    static Object failure(){return captureFailure==null?JSONObject.NULL:captureFailure;}
    static JSONObject click(ProbeService service,String scopeId,String observationId,String localId)throws Exception{
        require(scopeId);
        if(lastObservation==null||!observationId.equals(lastObservation.optString("observation_id")))throw new IllegalStateException("STALE_OBSERVATION");
        JSONObject expected=lastObservation.getJSONObject("tree");
        if(!expected.getBoolean("complete"))throw new IllegalStateException("PARTIAL_OBSERVATION");
        JSONObject selected=null;JSONArray nodes=expected.getJSONArray("nodes");String ready=null,dirty=null;int readyCount=0,dirtyCount=0;
        for(int i=0;i<nodes.length();i++){
            JSONObject node=nodes.getJSONObject(i);String rid=node.optString("resource_id","");
            if(localId.equals(node.getString("node_local_id")))selected=node;
            if(rid.equals(scope.pkg+":id/wfReady")&&node.getBoolean("visible")){ready=node.optString("text","");readyCount++;}
            if(rid.equals(scope.pkg+":id/wfOverallDirty")&&node.getBoolean("visible")){dirty=node.optString("text","");dirtyCount++;}
        }
        if(selected==null)throw new IllegalStateException("RESOLUTION_NOT_FOUND");
        String rid=selected.optString("resource_id","");
        if(!LearningScope.safeNavigation(scope.pkg,rid))throw new IllegalStateException("UNAUTHORIZED_ACTION");
        if(readyCount!=1||dirtyCount!=1)throw new IllegalStateException("AMBIGUOUS_PAGE_STATE");
        if(!("Ready".equals(ready)||"Ready / 就绪".equals(ready))
            ||!("Saved".equals(dirty)||"Saved / 全部已保存".equals(dirty)))throw new IllegalStateException("UNSAFE_PAGE_STATE");
        JSONObject fresh=snapshot(service,scope.pkg);
        if(fresh.getInt("window_id")!=lastObservation.getInt("window_id")||!fresh.getJSONObject("tree").toString().equals(expected.toString()))
            throw new IllegalStateException("STALE_OBSERVATION");
        AccessibilityNodeInfo root=null,target=null;
        List<AccessibilityNodeInfo> matches=null;
        try{
            if(Build.VERSION.SDK_INT>=33)service.clearCache();
            root=freshRoot(service);guard(service,root,scope.pkg);
            matches=root.findAccessibilityNodeInfosByViewId(rid);
            if(matches==null||matches.isEmpty())throw new IllegalStateException("RESOLUTION_NOT_FOUND");
            if(matches.size()!=1)throw new IllegalStateException("RESOLUTION_AMBIGUOUS");
            target=matches.get(0);Rect bounds=new Rect();target.getBoundsInScreen(bounds);
            JSONArray old=selected.getJSONArray("bounds");
            if(!target.isEnabled()||!target.isVisibleToUser()||!target.isClickable()
                ||bounds.left!=old.getInt(0)||bounds.top!=old.getInt(1)||bounds.right!=old.getInt(2)||bounds.bottom!=old.getInt(3))
                throw new IllegalStateException("STALE_NODE_ERROR");
            // No business inputs are authorized here; every click re-resolves a current unique node.
            scope.authorize(scopeId,observationId,SystemClock.elapsedRealtime());lastObservation=null;
            long before=SystemClock.uptimeMillis();boolean sent=target.performAction(AccessibilityNodeInfo.ACTION_CLICK);
            return new JSONObject().put("dispatch_id",UUID.randomUUID().toString()).put("observation_id",observationId)
                .put("scope_id",scopeId).put("node_local_id",localId).put("resource_id",rid)
                .put("started_uptime_ms",before).put("finished_uptime_ms",SystemClock.uptimeMillis())
                .put("dispatched",sent).put("input_api_calls",1).put("actor","AGENT_NAVIGATION")
                .put("actor_assurance","DUMP_PROTECTED_DETERMINISTIC_CONTROLLER").put("business_authorized",false);
        }finally{if(matches!=null)for(var node:matches)node.recycle();if(root!=null)root.recycle();}
    }
    private static Object nullable(Object value){return value==null?JSONObject.NULL:value;}
    private static String clean(CharSequence value,boolean sensitive,JSONArray reasons){
        if(value==null)return null;if(sensitive)return "[REDACTED_EDITABLE]";
        String s=value.toString();
        // Compile once, not five times per node per observation. Redaction rules are unchanged.
        s=SECRET.matcher(s).replaceAll("[REDACTED_KEY]");s=BEARER.matcher(s).replaceAll("[REDACTED_CREDENTIAL]");
        s=CONTACT.matcher(s).replaceAll("[REDACTED_CONTACT]");s=PHONE.matcher(s).replaceAll("[REDACTED_CONTACT]");
        s=PATH.matcher(s).replaceAll("[REDACTED_PATH]");
        if(s.length()>TEXT_LIMIT){reasons.put("TEXT_LIMIT");s=s.substring(0,TEXT_LIMIT);}return s;
    }
    private static String role(String name){
        if(name.contains("SeekBar"))return "slider";if(name.contains("Switch")||name.contains("CheckBox"))return "switch";
        if(name.contains("RadioButton"))return "radio";if(name.contains("Button"))return "button";
        if(name.contains("EditText"))return "input";if(name.contains("TextView"))return "text";return "container";
    }
    private static void walk(AccessibilityNodeInfo node,String parent,int depth,JSONArray nodes,JSONArray reasons)throws Exception{
        if(nodes.length()>=MAX_NODES){reasons.put("NODE_LIMIT");return;}
        if(depth>MAX_DEPTH){reasons.put("DEPTH_LIMIT");return;}
        String id="n"+nodes.length(),name=node.getClassName()==null?"":node.getClassName().toString();
        Rect b=new Rect();node.getBoundsInScreen(b);var range=node.getRangeInfo();JSONObject r=null;
        if(range!=null)r=new JSONObject().put("min",range.getMin()).put("max",range.getMax()).put("value",range.getCurrent())
            .put("kind",range.getType()==AccessibilityNodeInfo.RangeInfo.RANGE_TYPE_INT?"int":range.getType()==AccessibilityNodeInfo.RangeInfo.RANGE_TYPE_PERCENT?"percent":"float");
        JSONObject row=new JSONObject().put("node_local_id",id).put("parent_local_id",nullable(parent))
            .put("package",nullable(node.getPackageName())).put("resource_id",nullable(node.getViewIdResourceName()))
            .put("class_name",name).put("role",role(name)).put("text",nullable(clean(node.getText(),node.isPassword()||node.isEditable(),reasons)))
            .put("content_description",nullable(clean(node.getContentDescription(),node.isPassword()||node.isEditable(),reasons)))
            .put("bounds",new JSONArray(new int[]{b.left,b.top,b.right,b.bottom})).put("visible",node.isVisibleToUser())
            .put("enabled",node.isEnabled()).put("clickable",node.isClickable()).put("checkable",node.isCheckable())
            .put("checked",node.isChecked()).put("selected",node.isSelected()).put("editable",node.isEditable())
            .put("password",node.isPassword()).put("heading",node.isHeading()).put("range",nullable(r))
            .put("collection",collection(node)).put("collection_item",collectionItem(node));
        nodes.put(row);
        for(int i=0;i<node.getChildCount();i++){
            if(nodes.length()>=MAX_NODES){reasons.put("NODE_LIMIT");break;}
            AccessibilityNodeInfo child=Build.VERSION.SDK_INT>=33?node.getChild(i,AccessibilityNodeInfo.FLAG_PREFETCH_DESCENDANTS_HYBRID
                |AccessibilityNodeInfo.FLAG_PREFETCH_UNINTERRUPTIBLE):node.getChild(i);
            if(child==null){reasons.put("CHILD_UNAVAILABLE");continue;}
            try{walk(child,id,depth+1,nodes,reasons);}finally{child.recycle();}
        }
    }
    private static Object collection(AccessibilityNodeInfo node)throws JSONException{
        var c=node.getCollectionInfo();return c==null?JSONObject.NULL:new JSONObject().put("rows",c.getRowCount())
            .put("columns",c.getColumnCount()).put("hierarchical",c.isHierarchical()).put("selection_mode",c.getSelectionMode());
    }
    private static Object collectionItem(AccessibilityNodeInfo node)throws JSONException{
        var c=node.getCollectionItemInfo();return c==null?JSONObject.NULL:new JSONObject().put("row_index",c.getRowIndex())
            .put("row_span",c.getRowSpan()).put("column_index",c.getColumnIndex()).put("column_span",c.getColumnSpan())
            .put("heading",c.isHeading()).put("selected",c.isSelected());
    }
    private static JSONObject snapshot(ProbeService service,String pkg)throws Exception{
        AccessibilityNodeInfo root=null;AccessibilityWindowInfo window=null;
        try{
            long t0=SystemClock.uptimeMillis();root=freshRoot(service);long t1=SystemClock.uptimeMillis();guard(service,root,pkg);long t2=SystemClock.uptimeMillis();
            window=root.getWindow();if(window==null)throw new IllegalStateException("WINDOW_UNAVAILABLE");
            long t3=SystemClock.uptimeMillis();JSONArray nodes=new JSONArray(),reasons=new JSONArray();walk(root,null,0,nodes,reasons);long t4=SystemClock.uptimeMillis();
            JSONObject tree=new JSONObject().put("nodes",nodes).put("root_readable",true).put("complete",reasons.length()==0).put("truncated_reasons",reasons);
            JSONObject identity=LearningIdentityReference.collect(service,root,tree);
            return new JSONObject().put("window_id",root.getWindowId()).put("display_id",window.getDisplayId())
                .put("identity_reference",identity)
                .put("profile",new JSONObject().put("root_ms",t1-t0).put("guard_ms",t2-t1).put("window_ms",t3-t2).put("walk_ms",t4-t3))
                .put("tree",tree);
        }finally{if(window!=null)window.recycle();if(root!=null)root.recycle();}
    }
    private static AccessibilityNodeInfo freshRoot(ProbeService service){
        if(Build.VERSION.SDK_INT>=33){
            service.clearCache();
            // API33+: wait for descendant prefetch rather than issuing one remote request per child.
            // Budget and two independent cache-invalidated observations stay unchanged.
            return service.getRootInActiveWindow(AccessibilityNodeInfo.FLAG_PREFETCH_DESCENDANTS_HYBRID
                |AccessibilityNodeInfo.FLAG_PREFETCH_UNINTERRUPTIBLE);
        }
        return service.getRootInActiveWindow();
    }
    private static void guard(ProbeService service,AccessibilityNodeInfo root,String pkg)throws Exception{
        if(root==null)throw new IllegalStateException("ROOT_UNAVAILABLE");
        if(!pkg.contentEquals(root.getPackageName()==null?"":root.getPackageName()))throw new IllegalStateException("WINDOW_MISMATCH");
        List<AccessibilityWindowInfo> windows=service.getWindows();boolean active=false;
        try{
            if(windows==null)throw new IllegalStateException("WINDOW_UNAVAILABLE");
            for(var w:windows){
                if(w.getId()==root.getWindowId()&&(w.isFocused()||w.isActive())&&w.getType()==AccessibilityWindowInfo.TYPE_APPLICATION)active=true;
                if((w.isFocused()||w.isActive())&&w.getId()!=root.getWindowId())throw new IllegalStateException("BLOCKED_BY_OVERLAY");
            }
            if(!active)throw new IllegalStateException("WINDOW_MISMATCH");
        }finally{if(windows!=null)for(var w:windows)w.recycle();}
    }
}
