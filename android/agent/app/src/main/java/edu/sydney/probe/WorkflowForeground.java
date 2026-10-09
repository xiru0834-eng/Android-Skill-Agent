package edu.sydney.probe;
import android.view.accessibility.AccessibilityNodeInfo;
import android.view.accessibility.AccessibilityWindowInfo;
import java.util.*;
/** Read focused-window ownership only; never inspect foreign text, titles or descendants. */
final class WorkflowForeground {
    static String read(ProbeService service){
        try {
            List<String> focused=new ArrayList<>();
            for(AccessibilityWindowInfo window:service.getWindows()){
                if(!window.isFocused()||window.getType()==AccessibilityWindowInfo.TYPE_ACCESSIBILITY_OVERLAY)continue;
                AccessibilityNodeInfo root=window.getRoot();
                try{focused.add(root==null||root.getPackageName()==null?null:root.getPackageName().toString());}
                finally{if(root!=null)root.recycle();}
            }
            return WorkflowForegroundPolicy.classify(focused);
        }catch(RuntimeException error){return "UNKNOWN";}
    }
}
