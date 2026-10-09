package edu.sydney.probe;
import android.view.accessibility.AccessibilityNodeInfo;
import android.os.SystemClock;
import java.util.*;
import java.util.concurrent.atomic.AtomicLong;

/** Android tree adapter. Candidates are retained for this resolution only, never replayed. */
final class AccessibilityBindingResolver {
    private static final AtomicLong GENERATIONS=new AtomicLong();
    private static final EnvironmentBinding.AccessibilityResolver RESOLVER=new EnvironmentBinding.AccessibilityResolver();
    static final class Resolved {
        final AccessibilityNodeInfo node;final String strategy,page;
        final EnvironmentBinding.Target target;final String identity;final boolean checkable,checked;
        final long generation;final int windowId;boolean consumed,dispatched;boolean recoveredStale;
        Resolved(AccessibilityNodeInfo n,String strategy,String page,EnvironmentBinding.Target target,long generation){
            node=n;this.strategy=strategy;this.page=page;this.target=target;this.generation=generation;windowId=n.getWindowId();
            identity=string(n.getPackageName())+"|"+string(n.getViewIdResourceName())+"|"+string(n.getClassName());checkable=n.isCheckable();checked=n.isChecked();
        }
    }
    static final class Frame {
        final AccessibilityNodeInfo root;final String page;
        Frame(AccessibilityNodeInfo root,String page){this.root=root;this.page=page;}
    }
    interface RootSource {Frame read();}
    static final class Result {
        final EnvironmentBinding.Status status;final Resolved resolved;final List<Integer> candidates;final String reason;
        Result(EnvironmentBinding.Status status,Resolved resolved,List<Integer> candidates,String reason){this.status=status;this.resolved=resolved;this.candidates=List.copyOf(candidates);this.reason=reason;}
    }
    /** Public three-outcome adapter, sharing the canonical matcher with the legacy runtime. */
    static Result resolve(String semantic,EnvironmentBinding.AppBinding binding,AccessibilityNodeInfo root,String page){
        EnvironmentBinding.Target target=semantic==null?null:binding.targets.get(semantic);
        if(target==null)return new Result(EnvironmentBinding.Status.NOT_FOUND,null,List.of(),"UNBOUND_TARGET");
        if(root==null)return new Result(EnvironmentBinding.Status.NOT_FOUND,null,List.of(),"NO_TREE");
        if(!binding.packageName.equals(string(root.getPackageName())))return new Result(EnvironmentBinding.Status.NOT_FOUND,null,List.of(),"WRONG_APP");
        List<AccessibilityNodeInfo> actual;
        try{actual=collect(root,target);}
        catch(EnvironmentBinding.Failure failure){
            // An incomplete runtime tree cannot authorize a unique match. Contract bugs still throw.
            if(!"TREE_LIMIT".equals(failure.getMessage()))throw failure;
            return new Result(EnvironmentBinding.Status.NOT_FOUND,null,List.of(),"TREE_LIMIT");
        }
        List<EnvironmentBinding.Node> nodes=new ArrayList<>();for(var node:actual)nodes.add(candidate(node,target));
        long generation=GENERATIONS.incrementAndGet();
        var tree=new EnvironmentBinding.Tree(generation,string(root.getPackageName()),page,nodes);
        var outcome=EnvironmentBinding.resolve(semantic,binding,tree);
        if(outcome.status!=EnvironmentBinding.Status.RESOLVED)return new Result(outcome.status,null,outcome.candidates,outcome.reason);
        AccessibilityNodeInfo selected=actual.get(outcome.match.index);
        if(!timedRefresh(selected,ResolverTimingProbe.SELECTED_REFRESH,-1))return new Result(EnvironmentBinding.Status.NOT_FOUND,null,List.of(),"STALE:"+target.key);
        try{RESOLVER.verifyRefresh(target,tree,outcome.match,candidate(selected,target));}
        catch(EnvironmentBinding.Failure e){return new Result(EnvironmentBinding.Status.NOT_FOUND,null,List.of(),e.getMessage());}
        return new Result(EnvironmentBinding.Status.RESOLVED,new Resolved(selected,outcome.match.strategy,page,target,generation),List.of(),"");
    }
    static Resolved resolve(AccessibilityNodeInfo root,EnvironmentBinding.Target target,String page){
        List<AccessibilityNodeInfo> actual=collect(root,target);
        List<EnvironmentBinding.Node> candidates=new ArrayList<>();
        for(var node:actual)candidates.add(candidate(node,target));
        long generation=GENERATIONS.incrementAndGet();
        var tree=new EnvironmentBinding.Tree(generation,string(root.getPackageName()),page,candidates);
        var match=RESOLVER.resolve(target,tree,generation,page);AccessibilityNodeInfo selected=actual.get(match.index);
        if(!timedRefresh(selected,ResolverTimingProbe.SELECTED_REFRESH,-1))throw new IllegalStateException("STALE:"+target.key);
        RESOLVER.verifyRefresh(target,tree,match,candidate(selected,target));
        return new Resolved(selected,match.strategy,page,target,generation);
    }
    private static List<AccessibilityNodeInfo> collect(AccessibilityNodeInfo root,EnvironmentBinding.Target target){
        var mark=ResolverTimingProbe.begin(ResolverTimingProbe.COLLECT);int count=-1;
        try{
            List<AccessibilityNodeInfo> actual=target.resourceId.isEmpty()?new ArrayList<>():new ArrayList<>(lookupById(root,target));
            EnvironmentBinding.need(actual.size()<=2048,"TREE_LIMIT");
            if(actual.isEmpty()){
                var fallback=ResolverTimingProbe.begin(ResolverTimingProbe.FALLBACK);int visited=0,outcome=-1;
                try{
                    ArrayDeque<AccessibilityNodeInfo> queue=new ArrayDeque<>();queue.add(root);
                    while(!queue.isEmpty()){
                        EnvironmentBinding.need(++visited<=2048,"TREE_LIMIT");
                        AccessibilityNodeInfo n=queue.removeFirst();actual.add(n);
                        for(int i=0;i<n.getChildCount();i++){AccessibilityNodeInfo child=n.getChild(i);if(child!=null)queue.add(child);}
                        EnvironmentBinding.need(queue.size()<=2048,"TREE_LIMIT");
                    }
                    outcome=1;
                }finally{ResolverTimingProbe.end(fallback,visited,actual.size(),outcome);}
            }
            count=actual.size();return actual;
        }finally{ResolverTimingProbe.end(mark,count,-1,count<0?-1:1);}
    }
    private static List<AccessibilityNodeInfo> lookupById(AccessibilityNodeInfo root,EnvironmentBinding.Target target){
        var mark=ResolverTimingProbe.begin(ResolverTimingProbe.ID_LOOKUP);int outcome=-1;
        try{var found=root.findAccessibilityNodeInfosByViewId(target.packageName+":id/"+target.resourceId);outcome=1;return found;}
        finally{ResolverTimingProbe.end(mark,-1,-1,outcome);}
    }
    private static boolean timedRefresh(AccessibilityNodeInfo node,int operation,int attempt){
        var mark=ResolverTimingProbe.begin(operation);int outcome=-1;
        try{boolean refreshed=node.refresh();outcome=refreshed?1:0;return refreshed;}
        finally{ResolverTimingProbe.end(mark,attempt,-1,outcome);}
    }
    static Resolved resolveFresh(RootSource source,EnvironmentBinding.Target target,String expectedPage,int window){
        for(int attempt=0;attempt<2;attempt++){
            Frame frame=source.read();EnvironmentBinding.need(frame!=null&&frame.root!=null,"NO_TREE");
            EnvironmentBinding.need(expectedPage.equals(frame.page),"PAGE_CHANGED");
            EnvironmentBinding.need(window<0||frame.root.getWindowId()==window,"WINDOW_CHANGED");
            try{
                if(!timedRefresh(frame.root,ResolverTimingProbe.ROOT_REFRESH,attempt))throw new IllegalStateException("STALE_TREE");
                Resolved result=resolve(frame.root,target,frame.page);result.recoveredStale=attempt>0;return result;
            }catch(IllegalStateException e){
                if(attempt>0||e.getMessage()==null||!e.getMessage().startsWith("STALE"))throw e;
            }
        }throw new IllegalStateException("STALE_TREE");
    }
    /** One-use action permit: reacquire the whole matching context, not just the old node. */
    static Resolved forAction(RootSource source,Resolved prior){
        if(prior==null||prior.consumed)throw new IllegalStateException("NODE_ALREADY_USED");prior.consumed=true;
        boolean stale=!timedRefresh(prior.node,ResolverTimingProbe.PRIOR_REFRESH,-1);
        Resolved fresh=resolveFresh(source,prior.target,prior.page,prior.windowId);
        EnvironmentBinding.need(prior.identity.equals(fresh.identity),"TARGET_CONTEXT_CHANGED");
        EnvironmentBinding.need(prior.checkable==fresh.checkable&&(!prior.checkable||prior.checked==fresh.checked),"TARGET_STATE_CHANGED");
        EnvironmentBinding.need(fresh.node.isVisibleToUser()&&fresh.node.isEnabled()&&!fresh.node.isPassword()&&!fresh.node.isEditable(),"UNUSABLE_TARGET");
        fresh.recoveredStale|=stale;fresh.consumed=true;return fresh;
    }
    static boolean click(RootSource source,Resolved prior){
        return click(source,prior,Long.MAX_VALUE);
    }
    static boolean click(RootSource source,Resolved prior,long deadline){
        Resolved fresh=forAction(source,prior);EnvironmentBinding.need(fresh.node.isClickable(),"NOT_CLICKABLE");
        return clickPrepared(fresh,deadline);
    }
    static boolean clickPrepared(Resolved fresh,long deadline){
        EnvironmentBinding.need(fresh!=null&&fresh.consumed&&!fresh.dispatched,"INPUT_PERMIT_INVALID");
        EnvironmentBinding.need(fresh.node.isClickable(),"NOT_CLICKABLE");
        // Fresh Binder reads also consume the original task budget. Never reset its clock.
        WorkflowTiming.requireBeforeDeadline(SystemClock.elapsedRealtime(),deadline);
        fresh.dispatched=true;
        return fresh.node.performAction(AccessibilityNodeInfo.ACTION_CLICK);
    }
    private static EnvironmentBinding.Node candidate(AccessibilityNodeInfo n,EnvironmentBinding.Target target){
        var mark=ResolverTimingProbe.begin(ResolverTimingProbe.CANDIDATE);int outcome=-1;
        try{
            String pkg=string(n.getPackageName()),resource=string(n.getViewIdResourceName()),prefix=pkg+":id/";
            if(resource.startsWith(prefix))resource=resource.substring(prefix.length());
            String cls=string(n.getClassName()),role=cls.equals("android.widget.Switch")?"switch":cls.equals("android.widget.RadioButton")?"radio":cls.equals("android.widget.CheckBox")?"checkbox":cls.equals("android.widget.SeekBar")?"slider":cls.equals("android.widget.Button")?"button":"text";
            Set<String> scopes=new HashSet<>();List<String> labels=new ArrayList<>();
            var ancestors=ResolverTimingProbe.begin(ResolverTimingProbe.ANCESTORS);int visited=0,ancestorOutcome=-1;
            try{
                AccessibilityNodeInfo parent=n.getParent();
                for(int depth=0;parent!=null&&depth<12;depth++,parent=parent.getParent()){
                    visited++;
                    AccessibilityNodeInfo first=parent.getChildCount()==0?null:parent.getChild(0);
                    if(first!=null&&"android.widget.TextView".equals(string(first.getClassName()))&&!first.isEditable()&&!first.isPassword()&&!string(first.getText()).isEmpty()){
                        labels.add(string(first.getText()));break;
                    }
                }
                ancestorOutcome=1;
            }finally{ResolverTimingProbe.end(ancestors,visited,-1,ancestorOutcome);}
            if(EnvironmentBinding.localScope(target.scopeText,labels))scopes.add(target.scopeText);
            var result=new EnvironmentBinding.Node(pkg,resource,string(n.getText()),string(n.getContentDescription()),cls,role,scopes,n.isEnabled(),n.isPassword()||n.isEditable());
            outcome=1;return result;
        }finally{ResolverTimingProbe.end(mark,-1,-1,outcome);}
    }
    private static String string(CharSequence value){return value==null?"":value.toString();}
}
