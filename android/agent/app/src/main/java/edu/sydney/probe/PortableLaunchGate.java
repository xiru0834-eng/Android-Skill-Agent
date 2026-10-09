package edu.sydney.probe;
/** Read-only launch readiness. A lifecycle event is diagnostic, never sufficient authority. */
final class PortableLaunchGate {
    private final String expected;private final long startElapsed,startUptime,deadline;
    private volatile long windowReceived=-1;
    private volatile int eventWindowId=-1;
    private long firstObserved=-1,lastObserved=-1;private int windowId=-1,samples;
    private final String self;
    private enum Owner { TARGET,SELF,FOREIGN,UNKNOWN }
    private static final class Witness {
        final Owner owner;final long uptime,received;
        Witness(Owner owner,long uptime,long received){this.owner=owner;this.uptime=uptime;this.received=received;}
    }
    private final java.util.LinkedHashMap<Integer,Witness> owners=new java.util.LinkedHashMap<>();
    private final java.util.ArrayDeque<java.util.Map<String,Object>> metadata=new java.util.ArrayDeque<>();
    private int metadataCount,metadataDropped;
    private java.util.Map<String,Object> foreignTransition=java.util.Map.of();
    PortableLaunchGate(String expected,long startElapsed,long startUptime,int budget){this(expected,startElapsed,startUptime,budget,"edu.sydney.probe");}
    PortableLaunchGate(String expected,long startElapsed,long startUptime,int budget,String self){this.expected=expected;this.startElapsed=startElapsed;this.startUptime=startUptime;deadline=startElapsed+budget;this.self=self;}
    void windowChanged(String pkg,long eventUptime,long receivedElapsed){if(expected.equals(pkg)&&eventUptime>=startUptime&&windowReceived<0)windowReceived=receivedElapsed;}
    synchronized void windowChanged(String pkg,long eventUptime,long receivedElapsed,int id){
        windowChanged(pkg,eventUptime,receivedElapsed);
        if(expected.equals(pkg)&&eventUptime>=startUptime&&id>=0)eventWindowId=id;
        // Current-task metadata may refuse, never authorize an input or store foreign UI.
        if(id<0||eventUptime<startUptime||receivedElapsed<startElapsed||receivedElapsed>=deadline
            ||eventUptime>startUptime+(receivedElapsed-startElapsed))return;
        Owner owner=pkg==null?Owner.UNKNOWN:expected.equals(pkg)?Owner.TARGET:self.equals(pkg)?Owner.SELF:Owner.FOREIGN;
        var previous=owners.get(id);
        if(previous!=null&&eventUptime<previous.uptime)return;
        if(previous!=null&&eventUptime==previous.uptime&&owner!=previous.owner)owner=Owner.UNKNOWN;
        owners.put(id,new Witness(owner,eventUptime,receivedElapsed));
        if(owners.size()>32)owners.remove(owners.keySet().iterator().next());
    }
    synchronized int foreignForegroundEvidence(java.util.List<Integer> foreground,long now){
        if(now<startElapsed||now>=deadline)return -1;
        for(int id:foreground){var witness=owners.get(id);
            if(witness!=null&&witness.owner==Owner.FOREIGN&&witness.received<=now)return id;
        }
        return -1;
    }
    synchronized java.util.Map<String,Object> foregroundOwnerWitness(java.util.List<Integer> foreground,long now){
        int id=foreignForegroundEvidence(foreground,now);if(id<0)return java.util.Map.of();
        var witness=owners.get(id);
        return java.util.Map.of("window_id",id,"owner","FOREIGN_REDACTED","event_uptime_ms",witness.uptime,"received_elapsed_ms",witness.received);
    }
    /** No source node or event payload is inspected. Metadata can only refuse input. */
    synchronized void metadataEvent(String pkg,long eventUptime,long receivedElapsed,int id,int type){
        metadataCount++;
        boolean ownerType=type==1||type==16||type==32||type==4096||type==2048;
        String validity=!ownerType&&type!=4194304?"UNSUPPORTED_TYPE":id<0?"NO_WINDOW_ID":
            eventUptime<startUptime||receivedElapsed<startElapsed?"PRE_TASK":
            receivedElapsed>=deadline?"EXPIRED":eventUptime>startUptime+(receivedElapsed-startElapsed)?"FUTURE_TIME":"CURRENT_TASK";
        String owner=pkg==null?"UNKNOWN":expected.equals(pkg)?"TARGET":self.equals(pkg)?"SELF":"FOREIGN_REDACTED";
        if(metadata.size()==64){metadata.removeFirst();metadataDropped++;}
        metadata.addLast(java.util.Map.of("type",type,"window_id",id,"event_uptime_ms",eventUptime,
            "received_elapsed_ms",receivedElapsed,"owner",owner,"validity",validity));
        // WINDOWS_CHANGED has no reliable owner. Never overwrite ownership with it.
        if(ownerType&&"CURRENT_TASK".equals(validity)){
            windowChanged(pkg,eventUptime,receivedElapsed,id);
            // Positive unapproved window transition cancels this task's authority.
            // A replacement window or return does not restore user authorization.
            if(type==32&&"FOREIGN_REDACTED".equals(owner)&&foreignTransition.isEmpty())
                foreignTransition=java.util.Map.of("source","CURRENT_TASK_FOREIGN_WINDOW_TRANSITION",
                    "window_id",id,"event_uptime_ms",eventUptime,"received_elapsed_ms",receivedElapsed);
        }
    }
    synchronized java.util.Map<String,Object> windowMetadata(){
        return java.util.Map.of("observed_count",metadataCount,"dropped",metadataDropped,
            "events",new java.util.ArrayList<>(metadata));
    }
    synchronized java.util.Map<String,Object> foreignTransitionWitness(long now){
        return now<startElapsed||foreignTransition.isEmpty()||now<(Long)foreignTransition.get("received_elapsed_ms")?java.util.Map.of():foreignTransition;
    }
    int eventWindowId(){return eventWindowId;}
    int knownWindowId(){return windowId>=0?windowId:eventWindowId;}
    boolean inputFloorPassed(long now){return now-startElapsed>=500;}
    // A fresh target event identifies a window for refusal only. It is not an input permit.
    boolean foreignForegroundWindow(int id){int known=windowId>=0?windowId:eventWindowId;return known>=0&&id>=0&&id!=known;}
    void invalidateWindow(){firstObserved=lastObserved=-1;windowId=-1;samples=0;}
    void observeWindow(String pkg,int id,long now){
        if(!expected.equals(pkg)||id<0||now<startElapsed||now<lastObserved){invalidateWindow();return;}
        if(windowId!=id||firstObserved<0||now-lastObserved>400){firstObserved=now;windowId=id;samples=0;}
        if(now!=lastObserved)samples++;
        lastObserved=now;
    }
    long eventReceivedElapsed(){return windowReceived;}
    int observedSamples(){return samples;}
    int remaining(long now){return (int)Math.max(0,deadline-now);}
    String state(long now,boolean cancelled,boolean servicePresent){
        if(cancelled)return "CANCELLED";
        if(!servicePresent)return "SERVICE_UNAVAILABLE";
        if(now>=deadline)return "LAUNCH_WINDOW_UNAVAILABLE";
        return now-startElapsed>=500&&samples>=2&&now>=lastObserved&&now-lastObserved<=400&&lastObserved-firstObserved>=200?"READY":"WAIT";
    }
}
