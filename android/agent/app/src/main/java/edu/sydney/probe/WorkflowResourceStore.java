package edu.sydney.probe;
import android.content.Context;
final class WorkflowResourceStore {
    static WorkflowResources read(Context context){
        var p=context.getSharedPreferences("workflow_resources",0);
        return new WorkflowResources(p.getInt("recordingMinutes",2),p.getInt("confirmationSeconds",4));
    }
}
