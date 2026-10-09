package edu.sydney.probe;

import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** Worker-owned evidence only. No Android nodes, permission or execution logic. */
final class PortableLaunchSession {
    final PortableLaunchGate gate;
    private Map<String,Object> current=new LinkedHashMap<>();
    private final List<Map<String,Object>> reads=new ArrayList<>();
    private int dropped;
    PortableLaunchSession(PortableLaunchGate gate){this.gate=gate;}
    void beginRead(long now){current=new LinkedHashMap<>();put("start_elapsed_ms",now);put("root_requested",false);}
    void put(String key,Object value){current.put(key,value);}
    void completeRead(String result,long now){
        put("end_elapsed_ms",now);put("read_status",result);
        var snapshot=Collections.unmodifiableMap(new LinkedHashMap<>(current));
        if(reads.size()<128)reads.add(snapshot);
        else{reads.set(127,snapshot);dropped++;}
    }
    Map<String,Object> latest(){return new LinkedHashMap<>(current);}
    List<Map<String,Object>> history(){return Collections.unmodifiableList(new ArrayList<>(reads));}
    int dropped(){return dropped;}
    static String owner(CharSequence pkg,String target,String probe){
        if(pkg==null)return "NULL";
        if(target.contentEquals(pkg))return "TARGET";
        if(probe.contentEquals(pkg))return "PROBE";
        return "FOREIGN_REDACTED";
    }
}
