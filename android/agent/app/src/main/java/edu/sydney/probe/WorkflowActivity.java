package edu.sydney.probe;

import android.app.*;
import android.os.*;
import android.content.Intent;
import android.widget.*;
import org.json.*;

/** Separate opt-in workbench; old switch workflows remain unchanged. */
public final class WorkflowActivity extends Activity {
    private LinearLayout column;
    private TextView state;
    private EditText goal;
    @Override public void onCreate(Bundle saved) {
        super.onCreate(saved);column=Ui.page(this);
        TextView title=text("","完整任务 / Recorded workflow");title.setTextSize(23);
        text("","Transfer Bench 三页实验。依次进入灯设置、修改开关和亮度并保存，再配置风扇并保存。每次操作后稍等，再做下一步。返回这里停止录制。");
        goal=new EditText(this);goal.setId(id("flowGoal"));goal.setSingleLine(false);goal.setHint("任务说明 / Demonstration goal");
        goal.setText("Turn on the reading lamp at 60% and turn on the fan at low speed.");Ui.field(goal);column.addView(goal);
        button("flowRecord","开始真人示范 / Record demonstration",()->record("HUMAN_DECLARED"));
        button("flowRecordTest","自动化示范测试 / Automated capture",()->record("AUTOMATED"));
        button("flowStop","停止 / STOP",()->{if(ProbeService.current()!=null)ProbeService.current().stopAll();refresh();});
        button("flowImport","导入技能草稿 / Import draft",()->files(false));
        button("flowReview","审核并保存 / Review and save",this::review);
        button("flowExport","导出已审核技能 / Export skill",()->files(true));
        button("learningLegacy","用本次旧录制学习候选 / Learn from this legacy recording",()->startActivity(new Intent(this,UserLearningActivity.class).putExtra("legacy",true)));
        button("flowRun","执行已审核任务 / Run reviewed task",()->{
            try {ProbeService s=ProbeService.current();if(s==null)throw new IllegalStateException("SERVICE_OFF");s.runWorkflow();openApp();}
            catch(RuntimeException e){state.setText("未执行 / "+e.getMessage());}
        });
        button("flowRefresh","刷新记录 / Refresh",this::refresh);state=text("flowState","");refresh();
    }
    private void record(String source) {
        ProbeService s=ProbeService.current();if(s==null){state.setText("请开启 Demo Probe 无障碍服务 / Service unavailable");return;}
        try{s.stopAll();s.workflowRecorder().start(goal.getText().toString(),source);openApp();s.teachingControls().show(true);}
        catch(RuntimeException e){state.setText("无法开始录制 / "+e.getMessage());}
    }
    private void openApp(){startActivity(new Intent().setClassName(WorkflowUi.PKG,WorkflowUi.PKG+".WorkflowActivity").putExtra("layout","multi"));}
    private void files(boolean exporting) {
        if(ProbeService.current()!=null)ProbeService.current().stopAll();
        startActivity(new Intent(this,SkillFileActivity.class).putExtra("workflow",true).putExtra("mode",exporting?"EXPORT":"IMPORT"));
    }
    private void review() {
        WorkflowStore store=new WorkflowStore(this);String draft=store.draft();
        if(draft==null||!store.sameVersion(draft)){state.setText("没有兼容草稿 / No compatible draft");return;}
        try {
            JSONObject s=WorkflowCodec.decode(draft);StringBuilder info=new StringBuilder("来源 / Source: "+s.getString("source")+"\n"+s.getString("goal")+"\n目标 / Goals: "+s.getJSONArray("finalGoals")+"\n");
            for(int i=0;i<s.getJSONArray("steps").length();i++){JSONObject step=s.getJSONArray("steps").getJSONObject(i);info.append(i+1).append(". ").append(step.getString("page")).append(" → ").append(step.getString("id")).append('\n');}
            info.append("只适用于同版实验 App。来源为文件声明；尚未逐页检查新设备绑定，执行时逐步验证。不自动运行。 / Review meaning; runtime checks bindings. Approval stays on this device.");
            new AlertDialog.Builder(this).setTitle("审核完整任务 / Review workflow").setMessage(info)
                .setNegativeButton("取消 / Cancel",null).setPositiveButton("保存 / Save",(d,w)->{if(!store.review(draft))state.setText("草稿已变化 / Draft changed");else refresh();}).show();
        }catch(Exception e){state.setText("无效草稿 / Invalid draft");}
    }
    private void refresh() {
        String current="";
        try {
            JSONObject trace;
            try(java.io.FileInputStream in=openFileInput("workflow-trace.json")){trace=new JSONObject(new String(in.readAllBytes(),java.nio.charset.StandardCharsets.UTF_8));}
            current=trace.getString("traceId");
            state.setText("本次录制（不是技能执行结果） / Current recording\n来源 / Source: "+trace.getString("source")+"\n状态 / End: "+trace.getString("end")+"\n有效变化 / Steps: "+trace.getJSONArray("steps").length()+"\n问题 / Error: "+trace.getString("error")+"\nTrace: "+current);
        }catch(Exception e){state.setText("暂无本机完整任务记录 / No local recording");}
        WorkflowStore store=new WorkflowStore(this);
        state.append("\n\n已保存资料 / Saved items\n草稿："+WorkflowRecordingPolicy.relation(current,traceId(store.draft()))
            +"\n已审核技能："+WorkflowRecordingPolicy.relation(current,traceId(store.approved()))
            +"\n\n历史执行结果（不表示本次录制成功） / Previous execution, not recording status\n"+store.result());
    }
    private String traceId(String raw){try{return new JSONObject(raw).optString("traceId");}catch(Exception e){return "";}}
    @Override protected void onResume(){super.onResume();if(state!=null)refresh();}
    private int id(String key){return getResources().getIdentifier(key,"id",getPackageName());}
    private TextView text(String key,String value){TextView t=Ui.label(column,value,14);if(!key.isEmpty())t.setId(id(key));return t;}
    private void button(String key,String label,Runnable action){Ui.action(column,key,label,action,false);}
}
