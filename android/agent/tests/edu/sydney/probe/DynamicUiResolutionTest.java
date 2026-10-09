package edu.sydney.probe;
import java.util.*;

public final class DynamicUiResolutionTest {
    static int checks;
    static final String PKG="edu.sydney.transferlab";
    static void ok(boolean value){checks++;if(!value)throw new AssertionError("check "+checks);}
    static EnvironmentBinding.Node n(String id,String text,String desc,String role,String scope,boolean enabled){
        return new EnvironmentBinding.Node(PKG,id,text,desc,"android.widget."+(role.equals("slider")?"SeekBar":"Button"),role,scope.isEmpty()?Set.of():Set.of(scope),enabled,false);
    }
    static EnvironmentBinding.Target t(String id,String text,String desc,String role,String scope){
        return new EnvironmentBinding.Target("brightness_control",PKG,id,text,desc,"",role,scope,Set.of("resolver"));
    }
    static EnvironmentBinding.Resolution r(EnvironmentBinding.Target target,List<EnvironmentBinding.Node> nodes){
        return EnvironmentBinding.resolve("brightness_control",new EnvironmentBinding.AppBinding(PKG,Map.of("brightness_control",target)),new EnvironmentBinding.Tree(1,PKG,"resolver",nodes));
    }
    public static void main(String[] args){
        var target=t("brightness","Brightness","Brightness control","slider","Light");
        for(int i=0;i<100;i++){
            var nodes=new ArrayList<>(List.of(n("brightness","changed","","slider","Light",true),n("other","Brightness","Brightness control","slider","Fan",true)));
            Collections.shuffle(nodes,new Random(i));var found=r(target,nodes);
            ok(found.status==EnvironmentBinding.Status.RESOLVED);ok(nodes.get(found.match.index).resourceId.equals("brightness"));ok(found.match.strategy.equals("ID"));
        }
        for(String language:List.of("Brightness","亮度")){
            var label=t("old",language,"","slider","Light");
            var correct=n("renamed",language,"","slider","Light",true);
            var found=r(label,List.of(n("other",language,"","slider","Fan",true),correct));
            ok(found.status==EnvironmentBinding.Status.RESOLVED&&found.match.index==1&&found.match.strategy.equals("SEMANTIC"));
            ok(r(label,List.of(correct,correct)).status==EnvironmentBinding.Status.AMBIGUOUS);
        }
        ok(r(target,List.of(n("new","","Brightness control","slider","Light",true))).status==EnvironmentBinding.Status.RESOLVED);
        var structural=t("","","","slider","Brightness");
        ok(r(structural,List.of(n("new","","","slider","Brightness",true))).match.strategy.equals("STRUCTURE"));
        ok(r(structural,List.of(n("new","","","slider","Fan",true))).status==EnvironmentBinding.Status.NOT_FOUND);
        var duplicate=r(target,List.of(n("brightness","","","slider","Light",true),n("brightness","","","slider","Fan",false)));
        ok(duplicate.status==EnvironmentBinding.Status.AMBIGUOUS&&duplicate.candidates.size()==2);
        ok(r(target,List.of(n("brightness","","","button","Light",true))).status==EnvironmentBinding.Status.NOT_FOUND);
        ok(r(target,List.of(n("brightness","","","slider","Light",false))).status==EnvironmentBinding.Status.NOT_FOUND);
        ok(r(target,List.of()).status==EnvironmentBinding.Status.NOT_FOUND);
        // Native Android buttons may expose transformed ALL-CAPS text. Opt-in only.
        var folded=new EnvironmentBinding.Target("brightness_control",PKG,"old","Light","","","button","Light",Set.of("resolver"),true);
        ok(r(folded,List.of(n("new","LIGHT","","button","Light",true))).status==EnvironmentBinding.Status.RESOLVED);
        ok(r(t("old","Light","","button","Light"),List.of(n("new","LIGHT","","button","Light",true))).status==EnvironmentBinding.Status.NOT_FOUND);
        ok(r(folded,List.of(n("a","LIGHT","","button","Light",true),n("b","Light","","button","Light",true))).status==EnvironmentBinding.Status.AMBIGUOUS);
        ok(!EnvironmentBinding.localScope("Light",List.of("Other room","Light")));
        ok(EnvironmentBinding.localScope("Light",List.of("Light","Screen title")));
        ok(!EnvironmentBinding.localScope("Light",List.of()));
        ok(EnvironmentBinding.resolve(null,new EnvironmentBinding.AppBinding(PKG,Map.of("brightness_control",target)),new EnvironmentBinding.Tree(1,PKG,"resolver",List.of())).status==EnvironmentBinding.Status.NOT_FOUND);
        var app=new EnvironmentBinding.AppBinding(PKG,Map.of("brightness_control",target));
        ok(EnvironmentBinding.resolve("missing",app,new EnvironmentBinding.Tree(1,PKG,"resolver",List.of())).status==EnvironmentBinding.Status.NOT_FOUND);
        ok(EnvironmentBinding.resolve("brightness_control",app,new EnvironmentBinding.Tree(1,"another.app","resolver",List.of())).status==EnvironmentBinding.Status.NOT_FOUND);
        ok(EnvironmentBinding.resolve("brightness_control",app,new EnvironmentBinding.Tree(1,PKG,"elsewhere",List.of())).status==EnvironmentBinding.Status.NOT_FOUND);
        try {t("","","","slider","");throw new AssertionError("role-only authorized");}catch(EnvironmentBinding.Failure expected){checks++;}
        System.out.println("DynamicUiResolutionTest PASS "+checks+" checks");
    }
}
