package edu.sydney.probe;

import android.app.Instrumentation;
import android.os.Bundle;
import android.content.SharedPreferences;
import java.util.Map;
import java.util.List;

/** Isolated instrumentation storage; never reads or clears the user's evidence/approvals. */
public final class TraceChecks extends Instrumentation {
    private int checks;
    @Override public void onCreate(Bundle args) { super.onCreate(args);start(); }
    @Override public void onStart() {
        Bundle result=new Bundle();
        SharedPreferences testPrefs=getTargetContext().getSharedPreferences("trace_checks",0);
        try {
            String pkg=ProbePolicy.TRANSFER_PACKAGE,a=pkg+":id/mainToggle",b=pkg+":id/otherToggle";
            DemoTrace trace=new DemoTrace();trace.setBaseline(Map.of(a,"checked=false",b,"checked=false"));
            trace.onClick(a,10);trace.completeClick(Map.of(a,"checked=true",b,"checked=false"));
            trace.onClick(b,20);trace.completeClick(Map.of(a,"checked=true",b,"checked=true"));
            TraceBundle bundle=TraceBundle.capture(java.util.UUID.randomUUID().toString(),pkg,"1","Turn both on",
                    TraceBundle.Source.ADB_TEST,TraceBundle.End.STOPPED,trace);
            String json=TraceCodec.encode(bundle);
            check(json.equals(TraceCodec.encode(TraceCodec.decode(json))),"roundtrip");
            for(String bad:List.of("{}","null",json+" x",json.replace("\"schemaVersion\":1","\"schemaVersion\":1.0"),
                    json.replace("\"schemaVersion\":1","\"schemaVersion\":1,\"schemaVersion\":1"),
                    json.replace("\"schemaVersion\":1","\"schemaVersion\":\"1\""),
                    json.replace("\"index\":1","\"index\":2"),json.replace("\"eventTime\":10","\"eventTime\":-1"),
                    json.replace("\"eventTime\":10","\"eventTime\":1e1"),json.replace("ADB_TEST","AUTOMATICALLY_HUMAN"),
                    json.replace("TARGET_STATES_ONLY","FULL_SCREEN"),json.replace("NOT_COLLECTED","VERIFIED"),
                    json.replace("\"goal\":","\"approved\":true,\"goal\":"),json.replace('"','\''),
                    json.substring(0,json.length()-1)," ".repeat(TraceCodec.MAX_BYTES+1))) reject(bad);
            testPrefs.edit().clear().commit();TraceStore store=new TraceStore(getTargetContext(),"trace_checks");
            check(store.load(pkg)==null,"empty");check(store.save(bundle),"save");
            TraceStore reopened=new TraceStore(getTargetContext(),"trace_checks");
            check(json.equals(TraceCodec.encode(reopened.load(pkg))),"reopen identical");
            check("READY_FOR_REVIEW".equals(reopened.load(pkg).candidateReason()),"local candidate");
            TraceBundle unfinished=TraceBundle.capture(bundle.traceId,pkg,"1",bundle.goal,bundle.source,TraceBundle.End.RECORDING,trace);
            check(store.save(unfinished),"checkpoint");
            check(reopened.load(pkg).candidate()==null,"interrupted not executable");
            testPrefs.edit().putString("bundle."+pkg,"{}").commit();
            try { reopened.load(pkg);throw new AssertionError("corrupt accepted"); }catch(IllegalArgumentException expected) { checks++; }
            check(store.save(bundle),"replace corrupt via new capture");
            check(store.remove(pkg,bundle.traceId),"explicit deletion");check(store.load(pkg)==null,"deleted");
            check(store.save(bundle),"save again");check(!store.remove(pkg,"old-id"),"stale delete denied");
            check(store.load(pkg)!=null,"stale delete preserved evidence");
            result.putString("result","TraceChecks passed: "+checks+" assertions; strict codec and isolated persistence");finish(-1,result);
        } catch(Throwable e) { result.putString("error",e.toString());finish(1,result); }
        finally { testPrefs.edit().clear().commit(); }
    }
    private void reject(String value) { try { TraceCodec.decode(value);throw new AssertionError("invalid accepted"); }catch(IllegalArgumentException expected) { checks++; } }
    private void check(boolean condition,String message) { if(!condition) throw new AssertionError(message);checks++; }
}
