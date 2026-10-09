package edu.sydney.probe;
import java.util.*;
public final class NamedWorkflowPolicyTest {
    static int checks;
    static void ok(boolean v){checks++;if(!v)throw new AssertionError("check "+checks);}
    static void bad(Runnable r){try{r.run();throw new AssertionError("accepted invalid input");}catch(IllegalArgumentException expected){checks++;}}
    public static void main(String[] args){
        var a=new NamedWorkflowPolicy.Entry("a".repeat(64),"Reading mode","raw-a");
        var b=new NamedWorkflowPolicy.Entry("b".repeat(64),"明亮模式","raw-b");
        ok(NamedWorkflowPolicy.add(List.of(a),b).size()==2);
        ok(NamedWorkflowPolicy.add(List.of(a),a).size()==1);
        bad(()->NamedWorkflowPolicy.add(List.of(a),new NamedWorkflowPolicy.Entry(b.id," reading MODE ",b.raw)));
        bad(()->NamedWorkflowPolicy.add(List.of(a),new NamedWorkflowPolicy.Entry(a.id,"Changed","new raw")));
        bad(()->NamedWorkflowPolicy.add(List.of(a),new NamedWorkflowPolicy.Entry(a.id,"Rename",a.raw)));
        bad(()->new NamedWorkflowPolicy.Entry(a.id," ",a.raw));
        bad(()->new NamedWorkflowPolicy.Entry(a.id,"Bad\nname",a.raw));
        bad(()->new NamedWorkflowPolicy.Entry(a.id,"a".repeat(61),a.raw));
        bad(()->new NamedWorkflowPolicy.Entry("unknown","name",a.raw));
        List<NamedWorkflowPolicy.Entry> full=new ArrayList<>();
        for(int i=0;i<20;i++)full.add(new NamedWorkflowPolicy.Entry(String.format("%064x",i),"Skill "+i,"raw"));
        bad(()->NamedWorkflowPolicy.add(full,b));
        ok(NamedWorkflowPolicy.add(full,full.get(0)).size()==20);
        ok(NamedWorkflowPolicy.name("  阅读模式  ").equals("阅读模式"));
        System.out.println("NamedWorkflowPolicyTest: "+checks+" checks passed");
    }
}
