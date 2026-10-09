package edu.sydney.probe;

public final class PortableLaunchViewportTest {
    static void need(boolean value) { if (!value) throw new AssertionError("launch viewport"); }
    public static void main(String[] args) {
        need(!PortableLaunchViewport.inside(308,0,1388,2340,0,0,1080,2340));
        need(PortableLaunchViewport.inside(0,0,1080,2340,0,0,1080,2340));
        need(PortableLaunchViewport.inside(0,24,1280,776,0,0,1280,800));
        need(PortableLaunchViewport.inside(120,220,800,1200,100,200,1000,1400));
        need(!PortableLaunchViewport.inside(-1,0,1079,2340,0,0,1080,2340));
        need(!PortableLaunchViewport.inside(0,-1,1080,2339,0,0,1080,2340));
        need(!PortableLaunchViewport.inside(0,0,1080,2341,0,0,1080,2340));
        need(!PortableLaunchViewport.inside(0,0,0,2340,0,0,1080,2340));
        need(!PortableLaunchViewport.inside(1080,0,0,2340,0,0,1080,2340));
        need(!PortableLaunchViewport.inside(0,0,1080,2340,0,0,0,2340));
        var gate = new PortableLaunchGate("room",1000,500,8000);
        gate.observeWindow("room",7,1300); gate.observeWindow("room",7,1500);
        need(gate.state(1500,false,true).equals("READY"));
        gate.invalidateWindow();
        need(gate.state(1501,false,true).equals("WAIT"));
        need(gate.remaining(1501)==7499);
        need(gate.state(9000,false,true).equals("LAUNCH_WINDOW_UNAVAILABLE"));
        System.out.println("PortableLaunchViewportTest PASS: 13 boundary and shared-deadline checks");
    }
}
