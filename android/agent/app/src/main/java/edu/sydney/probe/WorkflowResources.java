package edu.sydney.probe;
/** User-controlled resource protection, not a business workflow template. */
final class WorkflowResources {
    final int recordingMinutes,confirmationSeconds;
    WorkflowResources(int minutes,int seconds){
        if(minutes<1||minutes>10||seconds<2||seconds>10)throw new IllegalArgumentException("RESOURCE_RANGE");
        recordingMinutes=minutes;confirmationSeconds=seconds;
    }
    static WorkflowResources defaults(){return new WorkflowResources(2,4);}
    long recordingMs(){return recordingMinutes*60000L;}
    long confirmationMs(){return confirmationSeconds*1000L;}
    long runMs(int steps){if(steps<=0)throw new IllegalArgumentException("NO_STEPS");return 6000L+(confirmationMs()+2500L)*steps;}
}
