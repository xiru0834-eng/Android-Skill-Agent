package edu.sydney.probe;
public final class PortableLaunchGateTest {
    static void need(boolean ok){if(!ok)throw new AssertionError("portable launch gate");}
    public static void main(String[] args){
        var gate=new PortableLaunchGate("room",1000,500,8000);
        need(gate.state(1000,false,true).equals("WAIT"));
        gate.windowChanged("other",600,1100);need(gate.state(2000,false,true).equals("WAIT"));
        gate.windowChanged("room",499,1100);need(gate.state(2000,false,true).equals("WAIT"));
        gate.windowChanged("room",500,1100);need(gate.state(1299,false,true).equals("WAIT"));
        need(gate.state(1300,false,true).equals("WAIT")); // Events alone cannot prove readiness.
        gate.observeWindow("room",7,1300);need(gate.state(1300,false,true).equals("WAIT"));
        gate.observeWindow("room",7,1499);need(gate.state(1499,false,true).equals("WAIT"));
        gate.observeWindow("room",7,1500);need(gate.state(1500,false,true).equals("READY"));
        need(gate.remaining(1300)==7700);
        need(gate.state(1300,true,true).equals("CANCELLED"));
        need(gate.state(1300,false,false).equals("SERVICE_UNAVAILABLE"));
        need(gate.state(9000,false,true).equals("LAUNCH_WINDOW_UNAVAILABLE"));
        need(gate.remaining(9001)==0);
        need(gate.state(1901,false,true).equals("WAIT")); // Old read is not live permission.
        gate.observeWindow("other",7,1901);need(gate.state(1901,false,true).equals("WAIT"));
        gate.observeWindow("room",8,2000);gate.observeWindow("room",9,2200);
        need(gate.state(2200,false,true).equals("WAIT"));
        gate.invalidateWindow();need(gate.state(2500,false,true).equals("WAIT"));
        var noEvent=new PortableLaunchGate("room",1000,500,8000);
        noEvent.observeWindow("room",4,1100);noEvent.observeWindow("room",4,1300);
        need(noEvent.state(1300,false,true).equals("WAIT")); // Early observations must not move the input floor.
        noEvent.observeWindow("room",4,1500);need(noEvent.state(1500,false,true).equals("READY"));
        noEvent.observeWindow("room",4,1200);need(noEvent.state(1300,false,true).equals("WAIT"));
        noEvent.observeWindow("room",-1,1400);need(noEvent.state(1400,false,true).equals("WAIT"));
        var owner=new PortableLaunchGate("room",1000,500,8000);
        need(!owner.foreignForegroundWindow(9)); // Missing event never invents an owner.
        owner.windowChanged("room",499,1100,7);need(!owner.foreignForegroundWindow(9));
        owner.windowChanged("other",600,1100,7);need(!owner.foreignForegroundWindow(9));
        owner.windowChanged("room",600,1100,7);
        need(!owner.foreignForegroundWindow(7));need(owner.foreignForegroundWindow(9));
        need(!owner.foreignForegroundWindow(-1));
        need(owner.state(1300,false,true).equals("WAIT")); // Event identity can refuse, never authorize.
        System.out.println("PortableLaunchGateTest: event-independent fresh-window checks passed");
    }
}
