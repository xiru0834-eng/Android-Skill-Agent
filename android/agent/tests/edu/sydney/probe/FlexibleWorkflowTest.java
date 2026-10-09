package edu.sydney.probe;
import java.util.Arrays;

public final class FlexibleWorkflowTest {
    static int checks;
    static void yes(boolean b){checks++;if(!b)throw new AssertionError("check "+checks);}
    static void bad(Runnable r){checks++;try{r.run();}catch(IllegalArgumentException e){return;}throw new AssertionError("accepted invalid route");}
    public static void main(String[] args){
        FlexibleWorkflow.State s=new FlexibleWorkflow.State("overview",new int[]{0,40,0,3});
        s.apply("wfOpenLamp",null);s.apply("wfLampValue60",true);
        var commit=s.apply("wfLampSave",null);
        yes(Arrays.equals(commit.commitGoals,new Integer[]{null,60,null,null}));yes(s.complete());
        for(int n=0;n<30;n++){s.apply("wfOpenLamp",null);s.apply(n%2==0?"wfLampValue40":"wfLampValue60",true);s.apply("wfLampSave",null);}
        yes(s.complete());yes(s.goals()[0]==null);
        s=new FlexibleWorkflow.State("single",new int[]{0,40,0,3});
        s.apply("wfLampPower",true);s.apply("wfLampPower",false);s.apply("wfLampSave",null);
        yes(s.goals()[0]==0);yes(s.goals()[1]==null);yes(s.complete());
        s.apply("wfFanValue1",true);s.apply("wfFanCancel",null);yes(s.goals()[3]==null);
        s.apply("wfMulti",null);s.apply("wfOpenFan",null);s.apply("wfFanValue1",true);s.apply("wfFanSave",null);
        yes(s.goals()[3]==1);yes(s.page().equals("overview"));
        FlexibleWorkflow.State wrong=new FlexibleWorkflow.State("overview",new int[]{0,40,0,3});
        bad(()->wrong.apply("wfLampPower",true));bad(()->wrong.apply("wfReset",null));
        wrong.apply("wfOpenLamp",null);wrong.apply("wfLampPower",true);
        bad(()->wrong.apply("wfLampBack",null));yes(!wrong.complete());
        wrong.apply("wfLampCancel",null);yes(!wrong.complete());
        yes(FlexibleWorkflow.budgetMs(40)>FlexibleWorkflow.budgetMs(4));
        System.out.println("FlexibleWorkflowTest: "+checks+" assertions passed");
    }
}
