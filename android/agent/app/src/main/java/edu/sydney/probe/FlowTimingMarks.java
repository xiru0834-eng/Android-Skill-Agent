package edu.sydney.probe;
import java.util.*;
/** Bounded diagnostic metadata only; no state reads, nodes, permission or clock policy. */
final class FlowTimingMarks {
    private final List<Map<String,Object>> rows=new ArrayList<>();
    private int dropped;
    synchronized void add(String stage,long elapsed,String thread){
        if(rows.size()==64){dropped++;return;}
        rows.add(Map.of("stage",stage,"elapsed_ns",elapsed,"thread",thread));
    }
    synchronized List<Map<String,Object>> snapshot(){return List.copyOf(rows);}
    synchronized int dropped(){return dropped;}
}
