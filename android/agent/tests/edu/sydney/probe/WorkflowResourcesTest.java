package edu.sydney.probe;
public final class WorkflowResourcesTest {
    public static void main(String[] args){
        var d=WorkflowResources.defaults();
        if(d.recordingMs()!=120000||d.confirmationMs()!=4000||d.runMs(3)!=25500||d.runMs(21)<=d.runMs(3))throw new AssertionError("default budgets");
        if(new WorkflowResources(10,10).runMs(100)<=new WorkflowResources(1,2).runMs(100))throw new AssertionError("configurable budgets");
        for(int[] v:new int[][]{{0,4},{11,4},{2,1},{2,11}}){try{new WorkflowResources(v[0],v[1]);throw new AssertionError("invalid resource budget");}catch(IllegalArgumentException expected){}}
        try{d.runMs(0);throw new AssertionError("no steps");}catch(IllegalArgumentException expected){}
        System.out.println("WorkflowResourcesTest PASS: defaults, range, variable length, immutable settings");
    }
}
