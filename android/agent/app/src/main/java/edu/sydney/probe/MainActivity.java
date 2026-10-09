package edu.sydney.probe;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.os.Bundle;
import android.provider.Settings;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

public final class MainActivity extends Activity {
    private TextView status, saved, draft, result, steps;
    private String selected;
    private SkillStore store;
    private LinearLayout column;
    private boolean en;
    private TextView homeService,homeRecent;
    private Button homeSetup;
    private final android.os.Handler homeHandler=new android.os.Handler(android.os.Looper.getMainLooper());
    private final Runnable homePoll=new Runnable(){public void run(){refreshHome();homeHandler.postDelayed(this,1000);}};
    private String t(String zh,String english){return en?english:zh;}
    @Override protected void onCreate(Bundle state) {
        super.onCreate(state);
        store = new SkillStore(this);
        selected = getPreferences(MODE_PRIVATE).getString("selected", ProbePolicy.LAB_PACKAGE);
        en=getSharedPreferences("language_connection",0).getBoolean("english",false);draw();
    }
    private void draw(){
        column=Ui.page(this);
        Ui.toolbar(column,t("操作助手","Workflow assistant"),"homeLanguage",en?"中文":"English",()->{
            en=!en;getSharedPreferences("language_connection",0).edit().putBoolean("english",en).apply();draw();
        });
        Ui.gap(column,20);
        Ui.label(column,t("把操作，变成技能","Turn actions into skills"),28);
        Ui.label(column,t("亲手示范一次，核对后按需复用。","Demonstrate, review, then reuse when you need it."),14);
        homeService=text("homeService","");Ui.badge(homeService);
        homeSetup=Ui.action(column,"homeSetup",t("开启无障碍服务","Connect accessibility service"),()->startActivity(new Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS)),false);
        Ui.gap(column,20);
        Ui.entry(column,"namedLibrary",t("使用技能  →","Use a skill  →"),t("输入指令，或从已保存的流程中选择","Enter a command or choose a saved routine"),()->startActivity(new Intent(this,WorkflowLibraryActivity.class)),true);
        Ui.entry(column,"teachEntry",t("录制新流程  ＋","Teach a new routine  ＋"),t("亲手操作一次，核对后保存成技能","Demonstrate it, review the steps, then save"),()->startActivity(new Intent(this,TeachingActivity.class)),false);
        Ui.action(column,"portableEntry",t("跨设备参数房间","Cross-device parameter room"),()->startActivity(new Intent(this,PortableSkillActivity.class)),false);
        Ui.gap(column,24);
        Ui.label(column,t("技能与最近状态","Skills & recent status"),18);
        homeRecent=text("homeRecentStatus","");homeRecent.setTextSize(14);Ui.notice(homeRecent);
        Button recent=Ui.action(column,"teachLibrary",t("查看最近录制与指南  →","Latest recording & guide  →"),()->startActivity(new Intent(this,TeachingActivity.class).putExtra("library",true)),false);Ui.quiet(recent);recent.setGravity(android.view.Gravity.START|android.view.Gravity.CENTER_VERTICAL);
        Ui.gap(column,12);
        Ui.label(column,t("仅用于已授权的实验 App，不控制真实家电。","For authorised experimental apps only. No real appliances."),14);
        LinearLayout home=column,advanced=new LinearLayout(this);advanced.setOrientation(1);
        Button tools=Ui.action(home,"homeAdvanced",t("实验工具与设置  ＋","Experiment tools & settings  ＋"),()->{},false);
        Ui.quiet(tools);
        tools.setOnClickListener(v->{boolean show=advanced.getVisibility()!=android.view.View.VISIBLE;advanced.setVisibility(show?android.view.View.VISIBLE:android.view.View.GONE);tools.setText(show?t("收起实验工具  −","Hide experiment tools  −"):t("实验工具与设置  ＋","Experiment tools & settings  ＋"));});
        home.addView(advanced);advanced.setVisibility(android.view.View.GONE);column=advanced;
        text("",t("以下是历史实验入口。日常使用请选择上面的技能或教学。","Legacy research tools. For everyday use, choose My skills or Teach above."));
        button(column,"languageEntry",t("双开关文字控制（旧版）","Two-switch commands (legacy)"),()->startActivity(new Intent(this,LanguageActivity.class)));
        button(column,"guidedTest","引导流程自动化测试 / Guided automated test",()->startActivity(new Intent(this,TeachingActivity.class).putExtra("automatedTest",true)));
        button(column,"flowEntry","完整任务实验台 / Workflow workbench",()->startActivity(new Intent(this,WorkflowActivity.class)));
        LinearLayout apps = row(); button(apps, "selectLab", "SmartHome Lab", () -> select(ProbePolicy.LAB_PACKAGE));
        button(apps, "selectBench", "Transfer Bench", () -> select(ProbePolicy.TRANSFER_PACKAGE));
        status = text("status", "");
        button(column, "traceEvidence", "Local demonstration evidence", () ->
                startActivity(new Intent(this,TraceActivity.class).putExtra("package",selected)));
        button(column, "deployments", "Portable workflows", () -> {
            if (ProbeService.current() != null) ProbeService.current().stopAll();
            startActivity(new Intent(this,DeploymentActivity.class).putExtra("package",selected));
        });
        button(column, "twoStep", "Two-step skills", () -> {
            if (ProbeService.current() != null) ProbeService.current().stopAll();
            startActivity(new Intent(this,TwoStepActivity.class).putExtra("package",selected));
        });
        LinearLayout controls = row();
        button(controls, "record", "Record", () -> {
            ProbeService service = ProbeService.current();
            if (service != null) { service.startRecording(selected); openApp(selected); }
            else refresh();
        });
        button(controls, "stop", "STOP", () -> { if (ProbeService.current() != null) ProbeService.current().stopAll(); refresh(); });
        draft = text("draft", "");
        LinearLayout reviewRow = row();
        button(reviewRow, "review", "Review and save", this::review);
        button(reviewRow, "checkBinding", "Check binding", () -> {
            SwitchSkill candidate = store.loadDraft(selected);
            if (candidate == null || ProbeService.current() == null) { refresh(); return; }
            ProbeService.current().checkSkill(candidate); openApp(selected);
        });
        saved = text("saved", "");
        LinearLayout runs = row(); button(runs, "runOn", "Run ON", () -> run(true)); button(runs, "runOff", "Run OFF", () -> run(false));
        LinearLayout files = row();
        button(files, "exportSkill", "Export skill", () -> file("EXPORT"));
        button(files, "importSkill", "Import draft", () -> file("IMPORT"));
        result = text("result", "");
        LinearLayout extras = row(); button(extras, "refresh", "Refresh", this::refresh);
        button(extras, "", "Clear in-memory trace", () -> {
            if (ProbeService.current() != null) ProbeService.current().clearRecords();
            store.draft(selected, null);
            refresh();
        });
        button(column, "", "Accessibility settings", () -> startActivity(new Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS)));
        steps = text("", ""); refresh();
    }
    private void select(String pkg) {
        if (ProbeService.current() != null) ProbeService.current().stopAll();
        selected = pkg; getPreferences(MODE_PRIVATE).edit().putString("selected", pkg).apply(); refresh();
    }
    private void review() {
        SwitchSkill skill = store.loadDraft(selected);
        if (skill == null || !selected.equals(skill.appPackage)) { refresh(); return; }
        if (!store.canReview(selected)) {
            new AlertDialog.Builder(this).setMessage("Imported draft: check binding first, then return and review within 60 seconds. No new skill has been approved.")
                    .setPositiveButton("OK", null).show(); return;
        }
        new AlertDialog.Builder(this).setTitle("Save / replace this switch skill?")
                .setMessage(skill.resourceId + (store.imported(selected) ? "\nSource file claims: " : "\nObserved: ") + skill.demonstratedBefore + " → " + skill.defaultDesired
                        + "\nRuns accept ON/OFF and verify the current node state. The binding and boolean evidence are saved locally.")
                .setNegativeButton("Cancel", null).setPositiveButton("Save", (dialog, which) -> {
                    SwitchSkill current = store.loadDraft(skill.appPackage);
                    if (current == null || !SkillCodec.encode(current).equals(SkillCodec.encode(skill))
                            || !store.reviewDraft(skill.appPackage)) status.setText("Save failed, candidate changed or check expired");
                    else refresh();
                }).show();
    }
    private void file(String mode) {
        if (ProbeService.current() != null) ProbeService.current().stopAll();
        startActivity(new Intent(this, SkillFileActivity.class).putExtra("mode", mode).putExtra("package", selected));
    }
    private void run(boolean desired) {
        SwitchSkill skill = store.load(selected); ProbeService service = ProbeService.current();
        if (skill == null || service == null) { refresh(); return; }
        service.runSkill(skill, desired); openApp(skill.appPackage);
    }
    private void openApp(String pkg) {
        Intent intent = getPackageManager().getLaunchIntentForPackage(pkg);
        if (intent == null) { if (ProbeService.current() != null) ProbeService.current().stopAll(); status.setText("App unavailable"); }
        else { intent.addFlags(Intent.FLAG_ACTIVITY_REORDER_TO_FRONT | Intent.FLAG_ACTIVITY_SINGLE_TOP); startActivity(intent); }
    }
    @Override protected void onResume() { super.onResume();ProbeService service=ProbeService.current();
        if(service!=null&&TeachingOverlayPolicy.hideAtHome(service.workflowRecorder().active(),service.workflowRunning()))service.teachingControls().remove();
        boolean language=getSharedPreferences("language_connection",0).getBoolean("english",false);if(language!=en){en=language;draw();}else if(status!=null)refresh();homeHandler.removeCallbacks(homePoll);homeHandler.postDelayed(homePoll,1000); }
    @Override protected void onPause(){homeHandler.removeCallbacks(homePoll);super.onPause();}
    @Override protected void onDestroy(){homeHandler.removeCallbacks(homePoll);super.onDestroy();}
    private void refreshHome() {
        ProbeService service = ProbeService.current();
        if(homeService!=null){homeService.setText(service==null?t("○ 无障碍服务未连接 · 请在设置中开启","○ Accessibility disconnected · Enable it in Settings"):t("● 无障碍服务已连接","● Accessibility connected"));homeService.setTextColor(service==null?UiStyle.DANGER:UiStyle.ACCENT);}
        if(homeSetup!=null)homeSetup.setVisibility(service==null?android.view.View.VISIBLE:android.view.View.GONE);
        if(homeRecent!=null){String summary;
            if(service!=null&&(service.workflowRecorder().active()||service.isRecording()))summary=t("正在录制，请回到教学页结束录制。","Recording in progress. Return to teaching to finish.");
            else if(service!=null&&service.workflowRunning())summary=t("正在执行，可以在任务浮条中停止。","Execution in progress. Stop from the task bar.");
            else try{WorkflowStore workflows=new WorkflowStore(this);int count=workflows.entries().size();summary=en?count+" saved skills":t("已保存 ","")+count+" 条技能";
                try{org.json.JSONObject last=new org.json.JSONObject(workflows.result());summary+="\n"+UiCopy.runState(last.optString("status"),en);}catch(Exception ignored){}
            }catch(Exception e){summary=t("技能库暂不可读，请到“我的技能”查看详情。","Skill library unavailable. Open My skills for details.");}
            homeRecent.setText(summary);
        }
    }
    private void refresh() {
        refreshHome();ProbeService service = ProbeService.current();
        status.setText("Selected: " + selected + "\nService " + (service == null ? "OFF" : "ON")
                + " · recording=" + (service != null && service.isRecording()));
        draft.setText("Demonstration: " + (store.loadDraft(selected) != null ? store.imported(selected)
                ? "IMPORTED · check=" + store.checkReason(selected) + (store.canReview(selected) ? " · review available" : " · needs check") : "READY_FOR_REVIEW (saved draft)"
                : service == null ? "unavailable" : !selected.equals(service.recordingPackage())
                ? "NO_DEMONSTRATION" : service.draft().code));
        SwitchSkill skill = store.load(selected);
        saved.setText(skill == null ? "No reviewed skill for this app" : "Saved: " + skill.resourceId + "\nWorkflow: SET_CHECKED(desired)");
        result.setText("Last run\n" + store.result());
        StringBuilder details = new StringBuilder();
        if (service != null && selected.equals(service.recordingPackage())) {
            details.append("Steps: ").append(service.steps().size()).append(" · unmatched changes: ").append(service.unattributedChanges()).append('\n');
            for (DemoTrace.Step step : service.steps()) details.append(step.targetId).append('\n')
                    .append(step.before).append(" → ").append(step.after).append(" · ").append(step.outcome).append('\n');
        }
        steps.setText(details);
    }
    private TextView text(String id, String value) {
        TextView view = Ui.label(column,value,14);
        if (!id.isEmpty()) view.setId(getResources().getIdentifier(id, "id", getPackageName()));
        return view;
    }
    private LinearLayout row() { LinearLayout row = new LinearLayout(this); column.addView(row); return row; }
    private void button(LinearLayout parent, String id, String label, Runnable action) {
        Button b=Ui.action(parent,id,label,action,false);
        if(parent.getOrientation()==LinearLayout.HORIZONTAL){LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(0,-2,1);p.topMargin=Ui.dp(this,8);if(parent.getChildCount()>1)p.leftMargin=Ui.dp(this,8);b.setLayoutParams(p);}
    }
}
