package edu.sydney.probe;
import java.util.Arrays;
public final class WorkflowGoalsTest {
    static void yes(boolean v){if(!v)throw new AssertionError();}
    public static void main(String[] args){
        Integer[] lamp={1,60,null,null},fan={null,null,0,2},full={1,60,1,1};
        yes(WorkflowGoals.valid(2,4,lamp));yes(WorkflowGoals.valid(2,4,fan));yes(WorkflowGoals.valid(1,8,full));
        yes(!WorkflowGoals.valid(1,4,lamp));yes(!WorkflowGoals.valid(2,8,full));
        yes(!WorkflowGoals.valid(2,4,new Integer[]{1,null,null,null}));yes(!WorkflowGoals.valid(2,4,new Integer[4]));
        for(int power=0;power<=1;power++)for(int speed=1;speed<=3;speed++){
            int[] initial={0,40,power,speed};int[] expected={1,60,power,speed};
            yes(Arrays.equals(WorkflowGoals.bind(lamp,initial),expected));yes(Arrays.equals(initial,new int[]{0,40,power,speed}));
            yes(WorkflowGoals.preserved(lamp,expected,expected));int[] changed=expected.clone();changed[2]=1-power;
            yes(!WorkflowGoals.preserved(lamp,expected,changed));
        }
        yes(Arrays.equals(WorkflowGoals.bind(fan,new int[]{0,80,1,3}),new int[]{0,80,0,2}));
        yes(!WorkflowGoals.valid(2,4,new Integer[]{1,61,null,null}));
        System.out.println("WorkflowGoalsTest PASS: scope, binding, preservation, old version");
    }
}
