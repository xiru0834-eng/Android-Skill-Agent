package edu.sydney.probe;
import android.view.accessibility.AccessibilityNodeInfo;
import android.view.accessibility.AccessibilityWindowInfo;
import java.util.List;

/** Conservative read-only window gate. Does not dismiss dialogs or inspect foreign content. */
final class PortableWindowGuard {
    static AccessibilityBindingResolver.Frame frame(AccessibilityNodeInfo root,List<AccessibilityWindowInfo> windows){
        if(root==null){
            int apps=0;if(windows!=null)for(var w:windows)if(w.getType()==AccessibilityWindowInfo.TYPE_APPLICATION)apps++;
            throw new IllegalStateException(PortableWindowReadPolicy.failure(false,windows==null?-1:windows.size(),apps));
        }
        boolean target=PortableSkillCodec.PKG.contentEquals(root.getPackageName());
        if(windows==null)throw new IllegalStateException("ROOT_READ_FAILED");
        if(windows.isEmpty())throw new IllegalStateException("STALE_WINDOWS");
        // Android may omit the completely occluded target window. Its absence cannot
        // authorize an input into a foreign active window or distinguish a dialog from navigation.
        if(!target)throw new IllegalStateException("BLOCKED_BY_OVERLAY");
        // An active editing session is unsafe even during the IME's opening animation.
        var focused=root.findFocus(AccessibilityNodeInfo.FOCUS_INPUT);
        try{if(focused!=null&&focused.isEditable())throw new IllegalStateException("BLOCKED_BY_OVERLAY");}
        finally{if(focused!=null)focused.recycle();}
        int layer=Integer.MIN_VALUE;
        for(var w:windows){
            if(w.getId()==root.getWindowId())layer=w.getLayer();
        }
        if(layer==Integer.MIN_VALUE)throw new IllegalStateException("STALE_WINDOWS");
        for(var w:windows){
            if(w.getId()==root.getWindowId()||w.getLayer()<layer)continue;
            if(w.getType()==AccessibilityWindowInfo.TYPE_INPUT_METHOD||w.getType()==AccessibilityWindowInfo.TYPE_ACCESSIBILITY_OVERLAY
                ||w.getType()==AccessibilityWindowInfo.TYPE_APPLICATION||w.isActive()||w.isFocused())throw new IllegalStateException("BLOCKED_BY_OVERLAY");
        }
        var markers=root.findAccessibilityNodeInfosByViewId(PortableSkillCodec.PKG+":id/psPage");
        try{
            if(markers.size()!=1)throw new IllegalStateException("BLOCKED_BY_OVERLAY");
            String page=String.valueOf(markers.get(0).getText());
            if(page.equals("loading"))throw new IllegalStateException("PAGE_LOADING");
            return new AccessibilityBindingResolver.Frame(root,page);
        }finally{for(var marker:markers)marker.recycle();}
    }
}
