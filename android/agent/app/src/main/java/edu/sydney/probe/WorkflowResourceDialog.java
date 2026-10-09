package edu.sydney.probe;
import android.app.*;
import android.text.InputFilter;
import android.widget.*;

/** Uses the existing UI components; a running task keeps its frozen budgets. */
final class WorkflowResourceDialog {
    static void show(Activity host,boolean idle,boolean en,Runnable changed){
        if(!idle){Toast.makeText(host,en?"Stop recording or execution before changing budgets.":"请先停止录制或执行，再调整预算。",Toast.LENGTH_LONG).show();return;}
        WorkflowResources current=WorkflowResourceStore.read(host);
        LinearLayout box=Ui.column(host);box.setPadding(24,12,24,12);
        Ui.label(box,en?"Recording duration (1–10 minutes)":"录制时长（1–10 分钟）",16);
        EditText minutes=input(host,box,"teachRecordingMinutes",current.recordingMinutes,en?"Recording minutes":"录制分钟数");
        Ui.label(box,en?"Action confirmation (2–10 seconds)":"每步确认预算（2–10 秒）",16);
        EditText seconds=input(host,box,"teachConfirmationSeconds",current.confirmationSeconds,en?"Confirmation seconds":"每步确认秒数");
        Ui.label(box,en?"These are resource budgets, not step limits. Running tasks cannot extend their deadlines. File limit: 256 KiB.":"这是资源预算，不是步数限制。运行中不会延长截止时间。文件上限：256 KiB。",14);
        AlertDialog dialog=new AlertDialog.Builder(host).setTitle(en?"Resource budgets":"资源预算").setView(box)
            .setNegativeButton(en?"Cancel":"取消",null).setPositiveButton(en?"Save":"保存",null).create();
        dialog.setOnShowListener(d->dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(v->{
            try{
                WorkflowResources next=new WorkflowResources(Integer.parseInt(minutes.getText().toString()),Integer.parseInt(seconds.getText().toString()));
                if(!host.getSharedPreferences("workflow_resources",0).edit().putInt("recordingMinutes",next.recordingMinutes).putInt("confirmationSeconds",next.confirmationSeconds).commit())throw new IllegalStateException("STORE");
                dialog.dismiss();changed.run();
            }catch(Exception error){minutes.setError(en?"Use 1–10":"填写 1–10");seconds.setError(en?"Use 2–10":"填写 2–10");}
        }));dialog.show();
    }
    private static EditText input(Activity a,LinearLayout box,String key,int value,String label){
        EditText v=new EditText(a);v.setId(a.getResources().getIdentifier(key,"id",a.getPackageName()));v.setText(Integer.toString(value));
        v.setContentDescription(label);v.setInputType(android.text.InputType.TYPE_CLASS_NUMBER);v.setFilters(new InputFilter[]{new InputFilter.LengthFilter(2)});Ui.field(v);box.addView(v);return v;
    }
}
