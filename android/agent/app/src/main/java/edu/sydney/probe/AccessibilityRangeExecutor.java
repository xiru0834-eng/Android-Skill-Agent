package edu.sydney.probe;
import android.accessibilityservice.*;
import android.graphics.Path;
import android.graphics.Rect;
import android.os.Bundle;
import android.os.SystemClock;
import android.view.accessibility.AccessibilityNodeInfo;

/** Input receipts only; callers MUST reacquire and verify state after completion. */
final class AccessibilityRangeExecutor {
    interface Completion {void inputFinished(boolean accepted,String method);}
    static RangeControl.Plan plan(AccessibilityNodeInfo node,double desired,RangeControl.Track reviewed){
        var range=node.getRangeInfo();if(range==null)throw new IllegalArgumentException("NO_RANGE");
        if(range.getType()==AccessibilityNodeInfo.RangeInfo.RANGE_TYPE_INT&&desired!=Math.rint(desired))throw new IllegalArgumentException("INTEGER_RANGE");
        boolean direct=node.getActionList().stream().anyMatch(a->a.getId()==AccessibilityNodeInfo.AccessibilityAction.ACTION_SET_PROGRESS.getId());
        Rect b=new Rect();node.getBoundsInScreen(b);
        return RangeControl.plan(range.getMin(),range.getMax(),range.getCurrent(),desired,direct,new RangeControl.Bounds(b.left,b.top,b.right,b.bottom),reviewed);
    }
    static boolean setProgress(AccessibilityBindingResolver.RootSource source,AccessibilityBindingResolver.Resolved prior,double desired){
        return setProgress(source,prior,desired,Long.MAX_VALUE);
    }
    /** Task callers supply the original monotonic deadline; validation time stays in that budget. */
    static boolean setProgress(AccessibilityBindingResolver.RootSource source,AccessibilityBindingResolver.Resolved prior,double desired,long deadline){
        return setPreparedProgress(AccessibilityBindingResolver.forAction(source,prior),desired,deadline);
    }
    static boolean setPreparedProgress(AccessibilityBindingResolver.Resolved fresh,double desired,long deadline){
        EnvironmentBinding.need(fresh!=null&&fresh.consumed&&!fresh.dispatched,"INPUT_PERMIT_INVALID");
        var action=plan(fresh.node,desired,null);
        Bundle args=new Bundle();args.putFloat(AccessibilityNodeInfo.ACTION_ARGUMENT_PROGRESS_VALUE,(float)action.value);
        // Android API 24+. A rejected input does NOT authorize an automatic gesture retry.
        WorkflowTiming.requireBeforeDeadline(SystemClock.elapsedRealtime(),deadline);
        fresh.dispatched=true;
        return fresh.node.performAction(AccessibilityNodeInfo.AccessibilityAction.ACTION_SET_PROGRESS.getId(),args);
    }
    static void execute(AccessibilityService service,AccessibilityBindingResolver.RootSource source,AccessibilityBindingResolver.Resolved prior,double desired,RangeControl.Track reviewed,Completion completion){
        execute(service,source,prior,desired,reviewed,completion,Long.MAX_VALUE);
    }
    static void execute(AccessibilityService service,AccessibilityBindingResolver.RootSource source,AccessibilityBindingResolver.Resolved prior,double desired,RangeControl.Track reviewed,Completion completion,long deadline){
        var fresh=AccessibilityBindingResolver.forAction(source,prior);var action=plan(fresh.node,desired,reviewed);
        if(action.kind==RangeControl.Kind.SET_PROGRESS){
            Bundle args=new Bundle();args.putFloat(AccessibilityNodeInfo.ACTION_ARGUMENT_PROGRESS_VALUE,(float)action.value);
            WorkflowTiming.requireBeforeDeadline(SystemClock.elapsedRealtime(),deadline);
            completion.inputFinished(fresh.node.performAction(AccessibilityNodeInfo.AccessibilityAction.ACTION_SET_PROGRESS.getId(),args),"SET_PROGRESS");return;
        }
        // Never used by existing click workflows. A track needs explicit environment approval.
        Path path=new Path();path.moveTo(action.startX,action.y);path.lineTo(action.endX,action.y);
        WorkflowTiming.requireBeforeDeadline(SystemClock.elapsedRealtime(),deadline);
        boolean accepted=service.dispatchGesture(new GestureDescription.Builder().addStroke(new GestureDescription.StrokeDescription(path,0,250)).build(),new AccessibilityService.GestureResultCallback(){
            @Override public void onCompleted(GestureDescription d){completion.inputFinished(true,"BOUNDS_DRAG");}
            @Override public void onCancelled(GestureDescription d){completion.inputFinished(false,"BOUNDS_DRAG");}
        },null);
        if(!accepted)completion.inputFinished(false,"BOUNDS_DRAG");
    }
}
