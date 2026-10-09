package edu.sydney.probe;

import java.util.List;

/** Synthetic, virtual-clock diagnostic only; not a phone success-rate estimate. */
public final class TwoStepAblationTest {
    public static void main(String[] args) {
        int rows=0,baselineFalse=0,jointFalse=0;
        for(int interval:new int[]{100,200}) for(boolean a:new boolean[]{false,true})
            for(boolean b:new boolean[]{false,true}) for(boolean rollback:new boolean[]{false,true}) {
                TwoStepSkill skill=TwoStepTest.skill();
                TwoStepEngine joint=new TwoStepEngine(skill,List.of(a,b),0,3500);
                ReplayEngine first=new ReplayEngine(skill.steps.get(0),a,0,3500);
                ReplayEngine second=new ReplayEngine(skill.steps.get(1),b,0,3500);
                for(int t=800;t<=3000;t+=interval) {
                    // Identical externally supplied observations, independent of either policy.
                    boolean actualA=t>=1000?a:!a,actualB=t>=1600?b:!b;
                    if(rollback && t>=1600) actualA=!a;
                    List<ReplayEngine.Scene> scene=TwoStepTest.scene(actualA,actualB);
                    joint.observe(scene,t);
                    if(!"SUCCEEDED".equals(first.status)) first.observe(scene.get(0),t);
                    else second.observe(scene.get(1),t);
                }
                boolean baselineSuccess="SUCCEEDED".equals(first.status) && "SUCCEEDED".equals(second.status);
                boolean jointSuccess="SUCCEEDED".equals(joint.status);
                TwoStepTest.eq(true,baselineSuccess);TwoStepTest.eq(!rollback,jointSuccess);
                rows++;if(rollback && baselineSuccess)baselineFalse++;if(rollback && jointSuccess)jointFalse++;
            }
        System.out.println("TwoStepAblationTest passed: synthetic traces="+rows+", accumulated-only falseSuccess="+baselineFalse+", joint falseSuccess="+jointFalse);
    }
}
