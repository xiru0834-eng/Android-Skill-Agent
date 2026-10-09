package edu.sydney.probe;

import android.content.Context;

/** A device-local presentation receipt, deliberately separate from task evidence. */
final class ExecutionCelebration {
    private ExecutionCelebration(){}
    static boolean claim(Context context,ExecutionResultData result,String expected){
        if(result==null||!result.valid)return false;
        var prefs=context.getSharedPreferences("execution_feedback",0);
        String key="shown-"+result.runId;
        if(!ExecutionResultPolicy.shouldCelebrate(result.status,result.runId,expected,prefs.getBoolean(key,false)?result.runId:"",SuccessFireworksView.animationsEnabled()))return false;
        // Mark before animation. A failed receipt must not cause repeated celebration.
        return prefs.edit().putBoolean(key,true).commit();
    }
}
