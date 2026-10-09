package edu.sydney.probe;
import java.util.*;

public final class EnvironmentBindingTest {
    static int checks;
    static void eq(Object a,Object b){checks++;if(!Objects.equals(a,b))throw new AssertionError(a+" != "+b);}
    static void reject(String code,Runnable r){checks++;try{r.run();throw new AssertionError("accepted "+code);}catch(EnvironmentBinding.Failure e){if(!code.equals(e.getMessage()))throw new AssertionError(code+" != "+e.getMessage());}}
    static EnvironmentBinding.Node node(String pkg,String id,String label,String scope,boolean enabled){
        return new EnvironmentBinding.Node(pkg,id,label,"","android.widget.Button","button",Set.of(scope),enabled,false);
    }
    static EnvironmentBinding.Target target(){
        return new EnvironmentBinding.Target("save","app.test","old_save","Save","保存","android.widget.Button","button","Lamp",Set.of("single","lamp"));
    }
    static EnvironmentBinding.Tree tree(List<EnvironmentBinding.Node> nodes){return new EnvironmentBinding.Tree(5,"app.test","single",nodes);}
    public static void main(String[] args){
        var resolver=new EnvironmentBinding.AccessibilityResolver();var t=target();
        var exact=node("app.test","old_save","Changed label","Lamp",true);
        var other=node("app.test","fan_save","Save","Fan",true);
        eq(0,resolver.resolve(t,tree(List.of(exact,other)),5,"single").index);
        eq("ID",resolver.resolve(t,tree(List.of(exact)),5,"single").strategy);
        var renamed=node("app.test","new_save","Save","Lamp",true);
        eq("SEMANTIC",resolver.resolve(t,tree(List.of(other,renamed)),5,"single").strategy);
        eq(1,resolver.resolve(t,tree(List.of(other,renamed)),5,"single").index);
        var description=new EnvironmentBinding.Node("app.test","new_save","New title","保存","android.widget.Button","button",Set.of("Lamp"),true,false);
        eq("SEMANTIC",resolver.resolve(t,tree(List.of(description)),5,"single").strategy);
        reject("AMBIGUOUS_ID",()->resolver.resolve(t,tree(List.of(exact,exact)),5,"single"));
        reject("AMBIGUOUS_TARGET",()->resolver.resolve(t,tree(List.of(renamed,renamed)),5,"single"));
        reject("MISSING_TARGET",()->resolver.resolve(t,tree(List.of(other)),5,"single"));
        reject("STALE_TREE",()->resolver.resolve(t,tree(List.of(exact)),6,"single"));
        reject("WRONG_PAGE",()->resolver.resolve(t,tree(List.of(exact)),5,"lamp"));
        reject("WRONG_PAGE",()->resolver.resolve(t,new EnvironmentBinding.Tree(5,"app.test","fan",List.of(exact)),5,"fan"));
        reject("WRONG_APP",()->resolver.resolve(t,new EnvironmentBinding.Tree(5,"app.other","single",List.of(exact)),5,"single"));
        reject("MISSING_TARGET",()->resolver.resolve(t,tree(List.of(node("app.other","old_save","Save","Lamp",true))),5,"single"));
        reject("TARGET_CONTEXT_CHANGED",()->resolver.resolve(t,tree(List.of(node("app.test","old_save","Save","Fan",true),renamed)),5,"single"));
        reject("TARGET_DISABLED",()->resolver.resolve(t,tree(List.of(node("app.test","old_save","Save","Lamp",false))),5,"single"));
        reject("UNUSABLE_TARGET",()->resolver.resolve(t,tree(List.of(new EnvironmentBinding.Node("app.test","old_save","Save","","android.widget.Button","button",Set.of("Lamp"),true,true))),5,"single"));
        reject("TARGET_CONTEXT_CHANGED",()->resolver.resolve(t,tree(List.of(new EnvironmentBinding.Node("app.test","old_save","Save","","android.widget.EditText","text",Set.of("Lamp"),true,false))),5,"single"));
        // Extra controls and order changes do not authorize an index-based shortcut.
        for(int position=0;position<16;position++){
            List<EnvironmentBinding.Node> nodes=new ArrayList<>();
            for(int i=0;i<16;i++)nodes.add(node("app.test","extra_"+i,"Save","Fan",true));
            nodes.add(position,renamed);eq(position,resolver.resolve(t,tree(nodes),5,"single").index);
            Collections.reverse(nodes);eq(nodes.size()-1-position,resolver.resolve(t,tree(nodes),5,"single").index);
        }
        eq("wfLampSave",TransferLabSelectors.target("wfLampSave").resourceId);
        var idTree=tree(List.of(exact,other));var idMatch=resolver.resolve(t,idTree,5,"single");
        // Previously a refresh could silently downgrade ID to a one-node semantic match.
        reject("TARGET_CONTEXT_CHANGED",()->resolver.verifyRefresh(t,idTree,idMatch,renamed));
        var semanticTree=tree(List.of(renamed,other));var semanticMatch=resolver.resolve(t,semanticTree,5,"single");
        reject("TARGET_CONTEXT_CHANGED",()->resolver.verifyRefresh(t,semanticTree,semanticMatch,node("app.test","another_save","Save","Lamp",true)));
        reject("TARGET_CONTEXT_CHANGED",()->resolver.verifyRefresh(t,semanticTree,semanticMatch,node("app.test","old_save","Save","Lamp",true)));
        eq("ID",resolver.verifyRefresh(t,idTree,idMatch,node("app.test","old_save","Updated title","Lamp",true)).strategy);
        eq("SEMANTIC",resolver.verifyRefresh(t,semanticTree,semanticMatch,renamed).strategy);
        reject("TARGET_DISABLED",()->resolver.verifyRefresh(t,idTree,idMatch,node("app.test","old_save","Save","Lamp",false)));
        reject("MATCH_CONTRACT",()->resolver.verifyRefresh(t,idTree,new EnvironmentBinding.Match(99,"ID"),exact));
        reject("MATCH_CONTRACT",()->resolver.verifyRefresh(t,idTree,new EnvironmentBinding.Match(0,"SEMANTIC"),exact));
        reject("TARGET_CONTEXT_CHANGED",()->resolver.verifyRefresh(t,idTree,idMatch,node("app.test","old_save","Save","Fan",true)));
        System.out.println("EnvironmentBindingTest passed: "+checks);
    }
}
