package edu.sydney.probe;

/** Narrow failure-context correction. Never changes an input or retry decision. */
final class WorkflowObservationReason {
    private WorkflowObservationReason(){}
    static String resolve(String original,String focusedOwner,boolean flexible){
        return flexible&&"MISSING:wfReady".equals(original)&&"OTHER".equals(focusedOwner)?"WRONG_APP":original;
    }
}
