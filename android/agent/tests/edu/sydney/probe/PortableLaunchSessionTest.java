package edu.sydney.probe;

/** A cancelled/in-flight run must never overwrite the next run's window audit. */
public final class PortableLaunchSessionTest {
    static void need(boolean value){if(!value)throw new AssertionError("launch session isolation");}
    public static void main(String[] args){
        var oldGate=new PortableLaunchGate("room",1000,500,8000);
        var newGate=new PortableLaunchGate("room",2000,1500,8000);
        var oldRun=new PortableLaunchSession(oldGate);
        var newRun=new PortableLaunchSession(newGate);
        oldGate.windowChanged("room",600,1100,7);
        newGate.windowChanged("room",1600,2100,9);
        need(oldRun.gate.knownWindowId()==7&&newRun.gate.knownWindowId()==9);
        oldRun.beginRead(1100);oldRun.put("root_owner","TARGET");oldRun.put("root_window_id",7);
        oldRun.completeRead("OK",1150);
        newRun.beginRead(2100);newRun.put("root_owner","PROBE");newRun.completeRead("LAUNCH_TRANSITION",2150);
        oldRun.beginRead(2200);oldRun.put("root_owner","TARGET");oldRun.completeRead("OK",2250);
        need(newRun.latest().get("root_owner").equals("PROBE"));
        need(newRun.history().size()==1&&oldRun.history().size()==2);
        need(oldGate.state(2250,false,true).equals("WAIT")); // Audit never permits an action.
        var copy=newRun.latest();copy.put("root_owner","TARGET");
        need(newRun.latest().get("root_owner").equals("PROBE"));
        newRun.beginRead(2300);newRun.completeRead("NO_TREE",2301);
        need(!newRun.latest().containsKey("root_owner")); // No old Root mixed into a new read.
        need(newRun.history().get(0).get("root_owner").equals("PROBE"));
        need(PortableLaunchSession.owner("room","room","probe").equals("TARGET"));
        need(PortableLaunchSession.owner("probe","room","probe").equals("PROBE"));
        need(PortableLaunchSession.owner("private.foreign.app","room","probe").equals("FOREIGN_REDACTED"));
        need(PortableLaunchSession.owner(null,"room","probe").equals("NULL"));
        for(int i=0;i<500;i++){newRun.beginRead(2400+i);newRun.completeRead("NO_TREE",2401+i);}
        need(newRun.history().size()==128&&newRun.dropped()==374);
        need(newRun.history().get(0).get("root_owner").equals("PROBE"));
        need(newRun.history().get(127).get("end_elapsed_ms").equals(2900L));
        need(newRun.gate.state(10000,false,true).equals("LAUNCH_WINDOW_UNAVAILABLE"));
        System.out.println("PortableLaunchSessionTest: isolation, retention, redaction and no-authority checks passed");
    }
}
