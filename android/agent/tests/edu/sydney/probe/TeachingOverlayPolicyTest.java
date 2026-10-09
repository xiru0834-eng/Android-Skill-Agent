package edu.sydney.probe;
public final class TeachingOverlayPolicyTest {
    public static void main(String[] args){
        if(!TeachingOverlayPolicy.hideAtHome(false,false))throw new AssertionError("completed overlay blocks home");
        for(boolean recording:new boolean[]{false,true})for(boolean running:new boolean[]{false,true}){
            if((recording||running)&&TeachingOverlayPolicy.hideAtHome(recording,running))throw new AssertionError("active controls hidden");
        }
        System.out.println("TeachingOverlayPolicyTest PASS: finished overlay hidden, active controls retained");
    }
}
