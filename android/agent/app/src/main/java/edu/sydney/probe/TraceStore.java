package edu.sydney.probe;

import android.content.Context;
import android.content.SharedPreferences;

/** One latest evidence bundle per allowed app. Does not read or grant any skill approval. */
public final class TraceStore {
    private final SharedPreferences prefs;
    public TraceStore(Context context) { this(context,"trace_bundles"); }
    TraceStore(Context context,String namespace) { prefs=context.getSharedPreferences(namespace,0); }
    public TraceBundle load(String pkg) {
        if(!ProbePolicy.allowed(pkg)) throw new IllegalArgumentException("Package");
        String value=prefs.getString("bundle."+pkg,null);if(value==null) return null;
        TraceBundle bundle=TraceCodec.decode(value);
        if(!pkg.equals(bundle.appPackage)) throw new IllegalArgumentException("Evidence package mismatch");return bundle;
    }
    public boolean save(TraceBundle bundle) {
        return prefs.edit().putString("bundle."+bundle.appPackage,TraceCodec.encode(bundle)).commit();
    }
    public boolean remove(String pkg,String expectedId) {
        TraceBundle bundle=load(pkg);
        if(bundle==null || !bundle.traceId.equals(expectedId)) return false;
        return prefs.edit().remove("bundle."+pkg).commit();
    }
}
