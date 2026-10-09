package edu.sydney.probe;

import android.app.*;
import android.content.*;
import android.os.Bundle;
import android.view.View;
import android.widget.*;
import org.json.*;

/** Viewing a result never teaches, selects or executes a workflow. */
public final class ExecutionResultActivity extends Activity {
    private String expected;
    private boolean en;
    private SuccessFireworksView fireworks;
    static Intent intent(Context context,String runId){return new Intent(context,ExecutionResultActivity.class).putExtra("runId",runId);}
    @Override public void onCreate(Bundle state){super.onCreate(state);expected=getIntent().getStringExtra("runId");en=getSharedPreferences("language_connection",0).getBoolean("english",false);draw();}
    private String t(String zh,String english){return en?english:zh;}
    private void draw(){
        LinearLayout body=Ui.page(this);
        Ui.toolbar(body,t("执行结果","Execution result"),"executionLanguage",en?"中文":"English",()->{en=!en;getSharedPreferences("language_connection",0).edit().putBoolean("english",en).apply();draw();},"executionBack",t("返回我的技能","Back to my skills"),this::skills);
        ExecutionResultData result=ExecutionResultData.read(this,expected);
        boolean valid=result!=null&&result.valid;
        boolean success=valid&&ExecutionResultPolicy.verified(result.status,result.runId,expected);
        Ui.gap(body,24);
        TextView heading=Ui.label(body,ExecutionResultPolicy.title(valid?result.status:"",valid,en),26);heading.setId(id("executionStatus"));heading.setAccessibilityLiveRegion(View.ACCESSIBILITY_LIVE_REGION_POLITE);
        if(success)heading.setTextColor(UiStyle.ACCENT);
        else if(!valid||!"RUNNING".equals(result.status))heading.setTextColor(UiStyle.WARNING);
        String message=!valid?t("没有找到这次执行的有效结果，不会拿其他任务的成功记录代替。","No valid result for this run. Another task's success will not be substituted."):
            success?t("全部最终目标已经核验。这里只查看结果，不会再次执行。","All final targets were verified. Viewing this result does not run the skill again."):
            "CANCELLED".equals(result.status)?t("后续操作已停止。已经发生的修改不会自动撤销。","Further actions stopped. Changes already made are not automatically undone."):
            "RUNNING".equals(result.status)?t("尚未取得最终结果，请完成后刷新。","No final result yet. Refresh after execution ends."):UiCopy.failure(result.reason,en);
        Ui.label(body,message,16);
        fireworks=null;
        if(success){
            SuccessFireworksView effect=new SuccessFireworksView(this);body.addView(effect,new LinearLayout.LayoutParams(-1,Ui.dp(this,84)));
            fireworks=effect;
            if(ExecutionCelebration.claim(this,result,expected))effect.play();
            else effect.setVisibility(View.GONE);
        }
        if(valid){
            LinearLayout details=Ui.panel(body);
            String name=t("历史流程","Recorded workflow");Integer total=null;
            try{var entry=new WorkflowStore(this).find(result.traceSha256);if(entry!=null){name=entry.name;total=WorkflowCodec.decode(entry.raw).getJSONArray("steps").length();}}catch(Exception ignored){}
            TextView skill=Ui.label(details,name,20);skill.setId(id("executionSkill"));
            try{JSONArray goals=result.raw.optJSONArray("goal");if(goals==null)goals=result.raw.optJSONArray("requestedGoals");
                if(goals!=null)Ui.label(details,TeachingGuide.goals(goals,en),16);
            }catch(Exception ignored){Ui.label(details,t("目标详情不可用；请查看技术记录。","Goal details unavailable; check the technical record."),14);}
            String metrics=t("执行耗时：","Execution time: ")+ExecutionResultPolicy.duration(result.elapsedMs,en)+"\n"+
                t("已确认步骤：","Confirmed steps: ")+result.completedSteps+(total==null?"":" / "+total)+"\n"+
                t("实际输入：","Actual inputs: ")+result.inputs+t(" 次","")+" · "+t("观察：","Observations: ")+result.observations+t(" 次","");
            TextView values=Ui.label(details,metrics,16);values.setId(id("executionMetrics"));
            Ui.label(details,t("耗时来自执行记录，不包含查看结果或烟花动画。","Time comes from the execution record; viewing and animation are excluded."),14);
            if(!success){TextView reason=Ui.label(details,t("停止原因：","Reason: ")+result.reason,14);reason.setId(id("executionReason"));}
            Ui.action(body,"executionDetails",t("查看技术详情","Technical details"),()->new AlertDialog.Builder(this).setTitle(t("本次执行记录","This run's record")).setMessage(result.raw.toString()).setPositiveButton(t("关闭","Close"),null).show(),false);
        }
        if(!valid||(valid&&"RUNNING".equals(result.status)))Ui.action(body,"executionRefresh",t("刷新结果","Refresh result"),this::draw,false);
        Ui.gap(body,16);
        Ui.action(body,"executionSkills",t("返回我的技能","Back to my skills"),this::skills,true);
        Ui.action(body,"executionHome",t("返回首页","Back to home"),()->{startActivity(new Intent(this,MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP));finish();},false);
    }
    private void skills(){startActivity(new Intent(this,WorkflowLibraryActivity.class).addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP));finish();}
    private int id(String name){return getResources().getIdentifier(name,"id",getPackageName());}
    @Override public void onBackPressed(){skills();}
    @Override protected void onPause(){if(fireworks!=null)fireworks.stop();super.onPause();}
}
