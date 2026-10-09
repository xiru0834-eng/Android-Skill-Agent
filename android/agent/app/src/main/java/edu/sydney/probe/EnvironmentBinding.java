package edu.sydney.probe;
import java.util.*;

/** Environment-only selectors and fresh-tree resolution. No Android or skill definitions. */
final class EnvironmentBinding {
    static final class Failure extends IllegalStateException {Failure(String reason){super(reason);}}
    static void need(boolean ok,String reason){if(!ok)throw new Failure(reason);}
    static final class Target {
        final String key,packageName,resourceId,text,description,className,role,scopeText;
        final Set<String> pages;
        final boolean asciiCaseInsensitive;
        Target(String key,String pkg,String id,String text,String description,String cls,String role,String scope,Set<String> pages){
            this(key,pkg,id,text,description,cls,role,scope,pages,false);
        }
        Target(String key,String pkg,String id,String text,String description,String cls,String role,String scope,Set<String> pages,boolean asciiCaseInsensitive){
            need(key!=null&&!key.isEmpty()&&pkg!=null&&!pkg.isEmpty(),"TARGET_CONTRACT");
            need(id!=null&&text!=null&&description!=null&&cls!=null&&role!=null&&scope!=null,"TARGET_CONTRACT");
            // A reviewed local label + role/class is evidence; a role alone is not.
            need(!id.isEmpty()||!text.isEmpty()||!description.isEmpty()||(!scope.isEmpty()&&(!cls.isEmpty()||!role.isEmpty())),"TARGET_CONTRACT");
            need(pages!=null&&!pages.isEmpty(),"TARGET_CONTRACT");
            this.key=key;packageName=pkg;resourceId=id;this.text=text;this.description=description;className=cls;this.role=role;scopeText=scope;this.pages=Set.copyOf(pages);this.asciiCaseInsensitive=asciiCaseInsensitive;
        }
    }
    static final class Node {
        final String packageName,resourceId,text,description,className,role;
        final Set<String> scopes;
        final boolean enabled,sensitive;
        Node(String pkg,String id,String text,String description,String cls,String role,Set<String> scopes,boolean enabled,boolean sensitive){
            need(pkg!=null&&id!=null&&text!=null&&description!=null&&cls!=null&&role!=null&&scopes!=null,"NODE_CONTRACT");
            packageName=pkg;resourceId=id;this.text=text;this.description=description;className=cls;this.role=role;this.scopes=Set.copyOf(scopes);this.enabled=enabled;this.sensitive=sensitive;
        }
    }
    static final class Tree {
        final long generation;final String packageName,page;final List<Node> nodes;
        Tree(long generation,String pkg,String page,List<Node> nodes){
            need(generation>0&&pkg!=null&&page!=null&&nodes!=null&&nodes.size()<=2048,"TREE_CONTRACT");
            this.generation=generation;packageName=pkg;this.page=page;this.nodes=List.copyOf(nodes);
        }
    }
    static final class Match {final int index;final String strategy;Match(int index,String strategy){this.index=index;this.strategy=strategy;}}
    enum Status {RESOLVED,AMBIGUOUS,NOT_FOUND}
    static final class AppBinding {
        final String packageName;final Map<String,Target> targets;
        AppBinding(String pkg,Map<String,Target> targets){
            need(pkg!=null&&!pkg.isEmpty()&&targets!=null&&targets.size()<=128,"APP_BINDING_CONTRACT");
            for(var entry:targets.entrySet())need(entry.getKey()!=null&&!entry.getKey().isEmpty()&&entry.getValue()!=null&&pkg.equals(entry.getValue().packageName),"APP_BINDING_CONTRACT");
            packageName=pkg;this.targets=Map.copyOf(targets);
        }
    }
    static final class Resolution {
        final Status status;final Match match;final List<Integer> candidates;final String reason;
        private Resolution(Status status,Match match,List<Integer> candidates,String reason){this.status=status;this.match=match;this.candidates=List.copyOf(candidates);this.reason=reason;}
    }
    static Resolution resolve(String semanticTarget,AppBinding binding,Tree tree){
        need(binding!=null&&tree!=null,"BINDING_NULL");Target target=semanticTarget==null?null:binding.targets.get(semanticTarget);
        if(target==null)return new Resolution(Status.NOT_FOUND,null,List.of(),"UNBOUND_TARGET");
        return new AccessibilityResolver().resolveResult(target,tree);
    }
    /** An inner room label is a boundary; never borrow a screen-level title beyond it. */
    static boolean localScope(String expected,List<String> nearestLabels){return !expected.isEmpty()&&!nearestLabels.isEmpty()&&expected.equals(nearestLabels.get(0));}
    interface Resolver {Match resolve(Target target,Tree current,long requiredGeneration,String expectedPage);}
    static final class AccessibilityResolver implements Resolver {
        Resolution resolveResult(Target target,Tree tree){
            try{return new Resolution(Status.RESOLVED,resolve(target,tree,tree.generation,tree.page),List.of(),"");}
            catch(Failure failure){
                String reason=failure.getMessage();
                if(reason.startsWith("AMBIGUOUS"))return new Resolution(Status.AMBIGUOUS,null,candidates(target,tree,reason.equals("AMBIGUOUS_ID")),reason);
                // Contract violations are programming errors, not a valid NOT_FOUND result.
                if(!Set.of("WRONG_APP","WRONG_PAGE","MISSING_TARGET","TARGET_CONTEXT_CHANGED","UNUSABLE_TARGET","TARGET_DISABLED").contains(reason))throw failure;
                return new Resolution(Status.NOT_FOUND,null,List.of(),reason);
            }
        }
        private List<Integer> candidates(Target target,Tree tree,boolean ids){
            List<Integer> out=new ArrayList<>();
            for(int i=0;i<tree.nodes.size();i++){
                Node n=tree.nodes.get(i);if(!target.packageName.equals(n.packageName))continue;
                boolean label=(!target.text.isEmpty()&&labelEquals(target,target.text,n.text))||(!target.description.isEmpty()&&labelEquals(target,target.description,n.description));
                boolean structural=target.resourceId.isEmpty()&&target.text.isEmpty()&&target.description.isEmpty();
                if(ids?target.resourceId.equals(n.resourceId):context(target,n)&&(label||structural))out.add(i);
            }return out;
        }
        Match verifyRefresh(Target target,Tree captured,Match selected,Node refreshed){
            need(captured!=null&&selected!=null&&refreshed!=null,"BINDING_NULL");
            need(selected.index>=0&&selected.index<captured.nodes.size(),"MATCH_CONTRACT");
            var permitted=resolve(target,captured,captured.generation,captured.page);
            need(permitted.index==selected.index&&permitted.strategy.equals(selected.strategy),"MATCH_CONTRACT");
            Node prior=captured.nodes.get(selected.index);
            // Refresh verifies this candidate; it must not grant a new identity or strategy.
            need(prior.packageName.equals(refreshed.packageName)&&prior.resourceId.equals(refreshed.resourceId)
                &&prior.className.equals(refreshed.className)&&prior.role.equals(refreshed.role),"TARGET_CONTEXT_CHANGED");
            var verified=resolve(target,new Tree(captured.generation,captured.packageName,captured.page,List.of(refreshed)),captured.generation,captured.page);
            need(verified.strategy.equals(selected.strategy),"TARGET_CONTEXT_CHANGED");
            return verified;
        }
        public Match resolve(Target target,Tree tree,long generation,String page){
            need(target!=null&&tree!=null,"BINDING_NULL");need(tree.generation==generation,"STALE_TREE");
            need(target.packageName.equals(tree.packageName),"WRONG_APP");
            need(tree.page.equals(page)&&target.pages.contains(page),"WRONG_PAGE");
            List<Integer> ids=new ArrayList<>(),semantic=new ArrayList<>();
            for(int i=0;i<tree.nodes.size();i++){
                Node n=tree.nodes.get(i);if(!target.packageName.equals(n.packageName))continue;
                if(!target.resourceId.isEmpty()&&target.resourceId.equals(n.resourceId))ids.add(i);
                boolean label=(!target.text.isEmpty()&&labelEquals(target,target.text,n.text))||(!target.description.isEmpty()&&labelEquals(target,target.description,n.description));
                boolean structural=target.resourceId.isEmpty()&&target.text.isEmpty()&&target.description.isEmpty();
                if((label||structural)&&context(target,n))semantic.add(i);
            }
            need(ids.size()<=1,"AMBIGUOUS_ID");
            List<Integer> selected=ids.isEmpty()?semantic:ids;
            need(!selected.isEmpty(),"MISSING_TARGET");need(selected.size()==1,"AMBIGUOUS_TARGET");
            int index=selected.get(0);Node n=tree.nodes.get(index);
            need(context(target,n),"TARGET_CONTEXT_CHANGED");need(!n.sensitive,"UNUSABLE_TARGET");need(n.enabled,"TARGET_DISABLED");
            return new Match(index,ids.isEmpty()?(target.resourceId.isEmpty()&&target.text.isEmpty()&&target.description.isEmpty()?"STRUCTURE":"SEMANTIC"):"ID");
        }
        private boolean context(Target t,Node n){
            return (t.className.isEmpty()||t.className.equals(n.className))&&(t.role.isEmpty()||t.role.equals(n.role))&&(t.scopeText.isEmpty()||n.scopes.contains(t.scopeText));
        }
        private boolean labelEquals(Target t,String expected,String actual){
            if(expected.equals(actual))return true;
            return t.asciiCaseInsensitive&&expected.chars().allMatch(c->c<128)&&actual.chars().allMatch(c->c<128)&&expected.equalsIgnoreCase(actual);
        }
    }
}
