package edu.sydney.probe;
import android.content.*;
import android.os.Bundle;
import android.view.accessibility.AccessibilityNodeInfo;
import android.graphics.Rect;
import org.json.*;
import java.util.*;
import java.io.*;

/** Shell-DUMP-only UI test adapter. Own Probe UI only, NEVER business App nodes. */
public final class ProductUiAuditReceiver extends BroadcastReceiver {
    private static final Set<String> seen=new HashSet<>();
    private static final Set<String> buttons=Set.of("portableEntry","publishedFlowReview","publishedFlowUnderstand","portableStop",
        "learningEntry","learningConnection","learningStart","learningStop","learningUseRecording","learningGenerate","learningSave","learningReload","learningValidate","learningCancel","learningBack","learningLanguage",
        "candidateReload","candidateBack","candidateValidate","candidateResult","candidateSaveName","candidatePublish","candidateLoadPublished","candidateCancel");
    private static final Set<String> fields=Set.of("portableInput","learningGoal","learningDocument","learningName","candidateName",
        "candidateValue0","candidateValue1","candidateValue2","candidateValue3","candidateValue4","candidateValue5","candidateValue6","candidateValue7");
    private static void need(boolean ok,String why){if(!ok)throw new IllegalArgumentException(why);}
    @Override public void onReceive(Context context,Intent intent){
        String rid=intent.getStringExtra("request_id");if(!"edu.sydney.probe.PRODUCT_UI_AUDIT".equals(intent.getAction())||rid==null||!rid.matches("[a-f0-9]{32}"))return;
        JSONObject out=new JSONObject();AccessibilityNodeInfo root=null;
        try{
            need(seen.size()<2048&&seen.add(rid),"AUDIT_REQUEST_LIMIT");var service=ProbeService.current();need(service!=null,"SERVICE_OFF");
            root=service.getRootInActiveWindow();need(root!=null&&"edu.sydney.probe".contentEquals(root.getPackageName()==null?"":root.getPackageName()),"OWN_UI_NOT_ACTIVE");
            String op=intent.getStringExtra("operation"),name=intent.getStringExtra("control");boolean acted=false;
            if("dump".equals(op)){
                JSONArray nodes=new JSONArray();tree(root,nodes,0);out.put("nodes",nodes);
            }else if("scroll".equals(op)||"scroll_back".equals(op)){
                acted=scroll(root,"scroll".equals(op)?AccessibilityNodeInfo.ACTION_SCROLL_FORWARD:AccessibilityNodeInfo.ACTION_SCROLL_BACKWARD);need(acted,"NO_SCROLLABLE_VIEW");
            }else{
                String resource;
                if("fill".equals(op)||"select".equals(op)){need(fields.contains(name),"UI_CONTROL_SCOPE");resource="edu.sydney.probe:id/"+name;}
                else if("confirm_dialog".equals(op)){need(intent.getBooleanExtra("confirmed",false),"EXPLICIT_UI_CONFIRMATION_REQUIRED");resource="android:id/button1";}
                else if("select_option".equals(op))resource=null;
                else{need("click".equals(op)&&buttons.contains(name),"UI_CONTROL_SCOPE");resource="edu.sydney.probe:id/"+name;}
                var nodes=resource==null?root.findAccessibilityNodeInfosByText(name):root.findAccessibilityNodeInfosByViewId(resource);
                if(resource==null){var it=nodes.iterator();while(it.hasNext()){var n=it.next();if(!name.contentEquals(n.getText()==null?"":n.getText())){n.recycle();it.remove();}}}
                try{
                    need(nodes.size()==1,"UI_CONTROL_NOT_UNIQUE");var node=nodes.get(0);
                    need(node.isVisibleToUser()&&node.isEnabled(),"UI_CONTROL_NOT_VISIBLE");
                    if("fill".equals(op)){
                        String raw;try(var f=context.openFileInput("product-ui-incoming.json")){raw=SkillFiles.read(f,8192);}var request=new JSONObject(raw);WorkflowCodec.fields(request,"request_id","text");
                        need(rid.equals(request.getString("request_id")),"UI_REQUEST_MISMATCH");String text=SemanticParameterCodec.text(request.getString("text"),"learningDocument".equals(name)?16000:2000);
                        Bundle values=new Bundle();values.putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE,text);acted=node.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT,values);
                    }else{need(node.isClickable(),"UI_NOT_CLICKABLE");acted=node.performAction(AccessibilityNodeInfo.ACTION_CLICK);}
                }finally{for(var n:nodes)n.recycle();}need(acted,"UI_ACTION_NOT_ACCEPTED");
            }
            out.put("status","OBSERVED_OR_UI_ACTION_ACCEPTED").put("ui_action_count",acted?1:0);
        }catch(Exception e){try{out.put("status","REJECTED").put("reason",e.getMessage()).put("ui_action_count",0);}catch(Exception ignored){}}
        finally{
            if(root!=null)root.recycle();try{
                out.put("request_id",rid).put("actor","EVALUATOR_UI_ACTION").put("business_app_access",false);
                var file=new android.util.AtomicFile(new File(context.getFilesDir(),"product-ui-audit-"+rid+".json"));FileOutputStream stream=null;
                try{stream=file.startWrite();stream.write(out.toString().getBytes(java.nio.charset.StandardCharsets.UTF_8));file.finishWrite(stream);}catch(Exception e){if(stream!=null)file.failWrite(stream);throw e;}
            }catch(Exception ignored){}
        }
    }
    private static boolean scroll(AccessibilityNodeInfo node,int action){
        if(node.isScrollable()&&node.performAction(action))return true;
        for(int i=0;i<node.getChildCount();i++){var child=node.getChild(i);if(child!=null)try{if(scroll(child,action))return true;}finally{child.recycle();}}return false;
    }
    private static void tree(AccessibilityNodeInfo node,JSONArray rows,int depth)throws Exception{
        if(depth>32||rows.length()>=256)return;Rect bounds=new Rect();node.getBoundsInScreen(bounds);
        String text=node.getText()==null?"":node.getText().toString();if(node.isPassword())text="[REDACTED]";else text=text.replaceAll("\\b[a-f0-9]{48}\\b","[REDACTED]");
        if(text.length()>600)text=text.substring(0,600);
        rows.put(new JSONObject().put("resource_id",node.getViewIdResourceName()).put("text",text).put("class",String.valueOf(node.getClassName()))
            .put("bounds",new JSONArray().put(bounds.left).put(bounds.top).put(bounds.right).put(bounds.bottom)).put("visible",node.isVisibleToUser()).put("clickable",node.isClickable()).put("checked",node.isChecked()).put("description",node.getContentDescription()));
        for(int i=0;i<node.getChildCount();i++){var child=node.getChild(i);if(child!=null)try{tree(child,rows,depth+1);}finally{child.recycle();}}
    }
}
