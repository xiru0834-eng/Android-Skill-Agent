package edu.sydney.probe;

import android.os.SystemClock;
import org.json.*;
import java.util.*;

/** Bounded receipt-only spans. No UI reads, authority, logging of task text or retained nodes. */
final class FlowTiming {
    private final List<Map<String,Object>> spans=new ArrayList<>();
    private final ThreadLocal<ArrayDeque<Integer>> parents=ThreadLocal.withInitial(ArrayDeque::new);
    private int sequence,dropped;
    private long deadline;
    private final ResolverTimingProbe.Buffer resolverBuffer=ResolverTimingProbe.ENABLED?new ResolverTimingProbe.Buffer():null;
    ResolverTimingProbe.Scope openResolverScope(){
        return ResolverTimingProbe.install(resolverBuffer,()->{var stack=parents.get();return stack.isEmpty()?0:stack.peek();});
    }
    private final FlowTimingMarks marks=new FlowTimingMarks();
    void mark(String phase){marks.add(phase,SystemClock.elapsedRealtimeNanos(),Thread.currentThread().getName());}
    final class Span implements AutoCloseable {
        private final int id,parent;private final String phase,thread;private final long start;
        private boolean closed;
        Span(String phase){
            this.phase=phase;thread=Thread.currentThread().getName();start=SystemClock.elapsedRealtimeNanos();
            var stack=parents.get();parent=stack.isEmpty()?0:stack.peek();
            synchronized(FlowTiming.this){id=++sequence;}stack.push(id);
        }
        public void close(){
            if(closed)return;closed=true;long end=SystemClock.elapsedRealtimeNanos();var stack=parents.get();
            if(!stack.isEmpty()&&stack.peek()==id)stack.pop();
            var row=new LinkedHashMap<String,Object>();row.put("id",id);row.put("parent_id",parent);row.put("phase",phase);
            row.put("thread",thread);row.put("start_ns",start);row.put("end_ns",end);row.put("duration_ms",(end-start)/1000000.0);
            row.put("remaining_ms",deadline==0?-1:deadline-end/1000000L);
            synchronized(FlowTiming.this){if(spans.size()<256)spans.add(row);else dropped++;}
        }
    }
    Span span(String phase){return new Span(phase);}
    void deadline(long value){deadline=value;}
    synchronized JSONObject receipt(String task,String plan)throws JSONException {
        var result=new JSONObject().put("clock","elapsedRealtimeNanos").put("scope","NESTED_INCLUSIVE_SPANS_DO_NOT_SUM")
            .put("task_id",task).put("plan_hash",plan).put("process_session",LearningCapture.PROCESS_SESSION)
            .put("deadline_elapsed_ms",deadline).put("spans",new JSONArray(spans)).put("dropped",dropped)
            .put("marks",new JSONArray(marks.snapshot())).put("marks_dropped",marks.dropped());
        if(resolverBuffer!=null)result.put("resolver_timing",resolverBuffer.json());
        return result;
    }
}
