package edu.sydney.probe;
import java.util.Set;
import java.util.concurrent.atomic.AtomicBoolean;
public final class FlowTaskGateTest {
    static String h="a".repeat(64);
    static void bad(Runnable f,String reason){try{f.run();throw new AssertionError("accepted "+reason);}catch(IllegalStateException e){if(!e.getMessage().equals(reason))throw e;}}
    public static void main(String[] args){
        var cancel=new AtomicBoolean();var approved=new AtomicBoolean(true);
        var gate=new FlowTaskGate(h,h,h,"task.fixture","host.phone","session.fixture",Set.of("bedroom_light.brightnessPercent"),100,8100,1,cancel,approved::get);
        gate.claim(h,h,h,100);
        bad(()->gate.authorizeCall("bedroom_ac.power",h,h,h,101),"UNAUTHORIZED_WRITE");
        gate.authorizeCall("bedroom_light.brightnessPercent",h,h,h,102);
        bad(()->gate.authorizeCall("bedroom_light.brightnessPercent",h,h,h,103),"ACTION_BUDGET_EXCEEDED");
        cancel.set(true);bad(()->gate.guard(h,h,h,104),"CANCELLED");cancel.set(false);
        approved.set(false);bad(()->gate.guard(h,h,h,105),"LOCAL_TASK_AUTHORIZATION_REQUIRED");approved.set(true);
        bad(()->gate.guard(h,h,h,99),"TASK_CLOCK_ERROR");
        bad(()->gate.guard(h,h,h,8100),"TASK_DEADLINE_EXCEEDED");
        gate.close();bad(()->gate.guard(h,h,h,106),"TASK_SESSION_NOT_ACTIVE");
        System.out.println("PASS FlowTaskGateTest");
    }
}
