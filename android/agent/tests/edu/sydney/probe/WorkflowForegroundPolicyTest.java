package edu.sydney.probe;
import java.util.*;
public final class WorkflowForegroundPolicyTest {
    public static void main(String[] args){
        check(WorkflowForegroundPolicy.classify(List.of("edu.sydney.transferlab")).equals("APP"),"lab focus");
        check(WorkflowForegroundPolicy.classify(List.of("edu.sydney.probe")).equals("CONTROLLER"),"controller focus");
        check(WorkflowForegroundPolicy.classify(List.of("com.android.settings")).equals("OTHER"),"foreign focus");
        check(WorkflowForegroundPolicy.classify(List.of()).equals("UNKNOWN"),"empty focus");
        check(WorkflowForegroundPolicy.classify(Arrays.asList((String)null)).equals("UNKNOWN"),"null root");
        check(WorkflowForegroundPolicy.classify(List.of(" ")).equals("UNKNOWN"),"empty package");
        check(WorkflowForegroundPolicy.classify(List.of("edu.sydney.transferlab","edu.sydney.transferlab")).equals("UNKNOWN"),"duplicate focus");
        check(WorkflowForegroundPolicy.classify(List.of("edu.sydney.transferlab","com.android.settings")).equals("UNKNOWN"),"conflicting focus");
        check(!WorkflowForegroundPolicy.expired(100,2099),"unknown early");
        check(WorkflowForegroundPolicy.expired(100,2100),"unknown boundary");
        check(!WorkflowForegroundPolicy.expired(-1,10000),"not unknown");
        System.out.println("WorkflowForegroundPolicyTest PASS: focused scope and unknown deadline");
    }
    private static void check(boolean condition,String name){if(!condition)throw new AssertionError(name);}
}
