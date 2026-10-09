package edu.sydney.probe;
public final class FlowTimingMarksTest {
    static void need(boolean ok){if(!ok)throw new AssertionError("timing marks");}
    public static void main(String[] args){
        var marks=new FlowTimingMarks();
        marks.add("flow_json_assembly.start",100,"worker");
        marks.add("flow_json_assembly.end",110,"worker");
        need(marks.snapshot().size()==2);
        need(marks.snapshot().get(0).get("elapsed_ns").equals(100L));
        try{marks.snapshot().clear();throw new AssertionError("mutable");}catch(UnsupportedOperationException expected){}
        var old=marks.snapshot();marks.add("next",120,"worker");need(old.size()==2);
        for(int i=0;i<100;i++)marks.add("bounded",130+i,"worker");
        need(marks.snapshot().size()==64&&marks.dropped()==39);
        System.out.println("PASS FlowTimingMarksTest bounded immutable metadata; no UI or authority");
    }
}
