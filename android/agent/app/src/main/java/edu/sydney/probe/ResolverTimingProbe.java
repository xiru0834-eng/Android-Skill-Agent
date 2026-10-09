package edu.sydney.probe;
import android.os.SystemClock;
import org.json.*;
import java.util.function.IntSupplier;

/** Diagnostic metadata only. This review proposal is not installed. */
final class ResolverTimingProbe {
    static final boolean ENABLED=true;
    static final int LIMIT=128;
    static final int COLLECT=0,ID_LOOKUP=1,FALLBACK=2,CANDIDATE=3,ANCESTORS=4,
        SELECTED_REFRESH=5,ROOT_REFRESH=6,PRIOR_REFRESH=7;
    private static final String[] NAMES={"collect","id_lookup","fallback","candidate","ancestors",
        "selected_refresh","root_refresh","prior_refresh"};
    private static final ThreadLocal<Scope> CURRENT=new ThreadLocal<>();
    static final class Buffer {
        final long[] start=new long[LIMIT],end=new long[LIMIT],thread=new long[LIMIT];
        final int[] parent=new int[LIMIT],flowParent=new int[LIMIT],operation=new int[LIMIT],
            countA=new int[LIMIT],countB=new int[LIMIT],result=new int[LIMIT];
        int size,dropped,recordingErrors;
        JSONObject json()throws JSONException{
            boolean ended=true;for(int i=0;i<size;i++)if(end[i]<0)ended=false;
            JSONArray rows=new JSONArray();
            for(int i=0;i<size;i++)rows.put(new JSONObject().put("id",i+1).put("parent_id",parent[i]+1)
                .put("flow_parent_id",flowParent[i]).put("phase",NAMES[operation[i]])
                .put("start_ns",start[i]).put("end_ns",end[i]<0?JSONObject.NULL:end[i])
                .put("thread_id",thread[i]).put("count_a",countA[i]).put("count_b",countB[i])
                .put("result_code",result[i]));
            return new JSONObject().put("clock","elapsedRealtimeNanos").put("limit",LIMIT)
                .put("spans",rows).put("dropped",dropped).put("recording_errors",recordingErrors)
                .put("complete",ended&&dropped==0&&recordingErrors==0)
                .put("interpretation","INCLUSIVE; NULL_END_IS_NOT_MEASURED; -1_RESULT_IS_EXCEPTION_OR_INCOMPLETE");
        }
    }
    static final class Scope implements AutoCloseable {
        final Scope previous;final Buffer buffer;final IntSupplier flowParent;int active=-1;boolean closed;
        Scope(Buffer buffer,IntSupplier flowParent){
            previous=CURRENT.get();this.buffer=buffer;this.flowParent=flowParent;
            if(buffer==null)CURRENT.remove();else CURRENT.set(this);
        }
        public void close(){
            if(closed)return;closed=true;
            if(previous==null)CURRENT.remove();else CURRENT.set(previous);
        }
    }
    static final class Mark {
        final Scope scope;final int index;
        Mark(Scope scope,int index){this.scope=scope;this.index=index;}
    }
    static Scope install(Buffer buffer,IntSupplier parent){return new Scope(buffer,parent);}
    static Mark begin(int operation){
        Scope scope=CURRENT.get();if(scope==null||scope.closed)return null;
        Buffer b=scope.buffer;
        try{
            if(b.size==LIMIT){b.dropped++;return null;}
            long start=SystemClock.elapsedRealtimeNanos();int flowParent=scope.flowParent.getAsInt();
            int i=b.size++;b.start[i]=start;b.end[i]=-1;b.result[i]=-1;
            b.countA[i]=-1;b.countB[i]=-1;b.thread[i]=Thread.currentThread().getId();
            b.operation[i]=operation;b.parent[i]=scope.active;b.flowParent[i]=flowParent;
            scope.active=i;return new Mark(scope,i);
        }catch(RuntimeException error){b.recordingErrors++;return null;}
    }
    static void end(Mark mark,int countA,int countB,int result){
        if(mark==null)return;Scope scope=mark.scope;Buffer b=scope.buffer;int i=mark.index;
        try{
            if(CURRENT.get()!=scope||scope.closed){b.recordingErrors++;return;}
            b.countA[i]=countA;b.countB[i]=countB;b.result[i]=result;
            b.end[i]=SystemClock.elapsedRealtimeNanos();
        }catch(RuntimeException error){b.recordingErrors++;}
        finally{scope.active=b.parent[i];}
    }
}
