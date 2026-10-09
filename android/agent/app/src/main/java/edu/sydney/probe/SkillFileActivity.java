package edu.sydney.probe;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.os.Bundle;
import android.os.CancellationSignal;
import android.os.Handler;
import android.os.ParcelFileDescriptor;
import android.widget.TextView;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** User-selected documents only. No exported intent filter and no automatic approval. */
public final class SkillFileActivity extends Activity {
    private static final int PICK = 1;
    private final Handler handler = new Handler();
    private final ExecutorService worker = Executors.newSingleThreadExecutor();
    private CancellationSignal signal;
    private TextView message;
    private String exportData;
    private boolean finished;
    private boolean processingStarted;
    private int generation;
    private boolean twoStep;
    private boolean deployment;
    private boolean workflow;
    private boolean namedWorkflow;
    private boolean en;
    private String t(String zh,String english){return en?english:zh;}

    @Override protected void onCreate(Bundle state) {
        super.onCreate(state);
        twoStep = getIntent().getBooleanExtra("twoStep", false);
        deployment = getIntent().getBooleanExtra("deployment", false);
        workflow = getIntent().getBooleanExtra("workflow", false);
        namedWorkflow = getIntent().getBooleanExtra("namedWorkflow", false);
        en=getSharedPreferences("language_connection",0).getBoolean("english",false);
        android.widget.LinearLayout page=Ui.page(this);
        boolean exporting = "EXPORT".equals(getIntent().getStringExtra("mode"));
        Ui.label(page,exporting?t("导出技能包","Export a skill package"):t("导入技能包","Import a skill package"),22);
        Ui.label(page,exporting?t("仅导出技能内容，不包含账户、审批或执行历史。","Only skill content is exported, not accounts, approvals or run history."):t("导入后还需要在本机审核。已有技能保留，不会自动执行。","Review is required on this device. Existing skills are kept; nothing runs automatically."),14);
        message=Ui.label(page,t("请在系统文件选择器中选择本地 JSON 文件。","Choose a local JSON file in the system file picker."),16);Ui.notice(message);
        Ui.action(page,"",t("返回","Back"),this::finish,false);
        if (ProbeService.current() != null) ProbeService.current().stopAll();
        if (state != null) {
            exportData = state.getString("exportData");
            if (state.getBoolean("processingStarted")) failure("File review was interrupted. Please select the file again; no new approval was saved.");
            return;
        }
        Intent picker = new Intent(exporting ? Intent.ACTION_CREATE_DOCUMENT : Intent.ACTION_OPEN_DOCUMENT)
                .addCategory(Intent.CATEGORY_OPENABLE).setType("application/json").putExtra(Intent.EXTRA_LOCAL_ONLY, true);
        if (exporting) {
            if (namedWorkflow) {
                try {var item=new WorkflowStore(this).find(getIntent().getStringExtra("skillId"));
                    if(item==null)throw new IllegalArgumentException();exportData=NamedWorkflowCodec.encode(item);
                    picker.putExtra(Intent.EXTRA_TITLE,"named-workflow-"+item.id.substring(0,8)+".json");
                }catch(Exception e){failure("No reviewed named skill to export.");return;}
            } else if (workflow) {
                exportData=new WorkflowStore(this).approved();
                if(exportData==null){failure("No reviewed workflow to export.");return;}
                picker.putExtra(Intent.EXTRA_TITLE,"recorded-workflow.json");
            } else if (deployment) {
                DeploymentSkill skill=new DeploymentStore(this).active();
                if(skill==null) {failure("No reviewed deployment to export.");return;}
                exportData=DeploymentCodec.encode(skill);
                picker.putExtra(Intent.EXTRA_TITLE,"workflow-"+skill.bindingId+".json");
            } else if (twoStep) {
                TwoStepSkill skill=new TwoStepStore(this).load(getIntent().getStringExtra("package"));
                if(skill==null) { failure("No reviewed two-step skill to export.");return; }
                exportData=TwoStepCodec.encode(skill);
                picker.putExtra(Intent.EXTRA_TITLE,"two-step-skill-"+skill.appPackage+".json");
            } else {
            SwitchSkill skill = new SkillStore(this).load(getIntent().getStringExtra("package"));
            if (skill == null) { failure("No reviewed skill to export."); return; }
            exportData = SkillCodec.encode(skill);
            picker.putExtra(Intent.EXTRA_TITLE, "switch-skill-" + skill.appPackage + ".json");
            }
        }
        try { startActivityForResult(picker, PICK); }
        catch (RuntimeException error) { failure("No document picker is available."); }
    }
    @Override protected void onSaveInstanceState(Bundle state) {
        state.putString("exportData", exportData); state.putBoolean("processingStarted", processingStarted);
        super.onSaveInstanceState(state);
    }
    @Override protected void onActivityResult(int request, int code, Intent data) {
        super.onActivityResult(request, code, data);
        if (request != PICK) return;
        if (code != RESULT_OK || data == null || data.getData() == null) { finish(); return; }
        processingStarted = true;
        if (!"content".equals(data.getData().getScheme())) { failure("Unsupported document location."); return; }
        message.setText(t("正在处理所选文件…","Processing selected file…"));
        int active = ++generation;
        CancellationSignal currentSignal = new CancellationSignal(); signal = currentSignal;
        String snapshot = exportData;
        handler.postDelayed(() -> {
            if (active != generation || finished) return;
            generation++; currentSignal.cancel();
            failure("File operation timed out. No skill was imported. An exported file may be incomplete.");
        }, 8000);
        worker.execute(() -> {
            try (ParcelFileDescriptor descriptor = getContentResolver().openFileDescriptor(data.getData(), snapshot == null ? "r" : "wt", currentSignal)) {
                if (descriptor == null) throw new java.io.IOException("Unavailable document");
                String imported = null;
                if (snapshot == null) {
                    try (ParcelFileDescriptor.AutoCloseInputStream stream = new ParcelFileDescriptor.AutoCloseInputStream(descriptor)) {
                        String json=SkillFiles.read(stream,(namedWorkflow||workflow)?FlexibleWorkflowCodec.LIMIT:SkillFiles.MAX_BYTES);
                        imported = namedWorkflow ? NamedWorkflowCodec.encode(NamedWorkflowCodec.decode(json)) : workflow ? WorkflowCodec.decode(json).toString() : deployment ? DeploymentCodec.encode(DeploymentCodec.decode(json))
                                : twoStep ? TwoStepCodec.encode(TwoStepCodec.decode(json)) : SkillCodec.encode(SkillCodec.decode(json));
                    }
                } else {
                    try (ParcelFileDescriptor.AutoCloseOutputStream stream = new ParcelFileDescriptor.AutoCloseOutputStream(descriptor)) {
                        stream.write(snapshot.getBytes(StandardCharsets.UTF_8)); stream.flush();
                    }
                }
                String valid = imported;
                handler.post(() -> {
                    if (active != generation || finished) return;
                    generation++;
                    if (valid == null) {
                        new AlertDialog.Builder(this).setMessage(t("技能包已导出。审批、账户和执行历史没有导出。","Skill exported. Approval, accounts and run history were not exported."))
                                .setPositiveButton(t("完成","Done"), (d, w) -> finish()).setOnCancelListener(d -> finish()).show();
                    } else confirmImport(valid);
                });
            } catch (Exception error) {
                handler.post(() -> {
                    if (active != generation || finished) return;
                    generation++; failure("File rejected or unavailable. Existing skills are unchanged.");
                });
            }
        });
    }
    private void confirmImport(String json) {
        if(namedWorkflow){
            var item=NamedWorkflowCodec.decode(json);
            new AlertDialog.Builder(this).setTitle(t("导入待审技能：","Import draft: ")+item.name)
                .setMessage(t("只导入草稿，不执行、不迁移审批。已有技能保留；请返回“我的技能”审核保存。","Draft only: no execution or approval transfer. Existing skills stay. Review and save in My skills."))
                .setNegativeButton(t("取消","Cancel"),(d,w)->finish()).setPositiveButton(t("导入草稿","Import draft"),(d,w)->{
                    if(new WorkflowStore(this).stageNamed(json))finish();else failure("Could not save pending package.");
                }).setOnCancelListener(d->finish()).show();return;
        }
        if(workflow) {
            new AlertDialog.Builder(this).setTitle("导入未审核任务 / Import unreviewed workflow?")
                .setMessage("只导入草稿，不运行、不迁移批准。请返回完整任务页面审核目标与步骤。 / Imported claims require review on this device.")
                .setNegativeButton("取消 / Cancel",(d,w)->finish()).setPositiveButton("导入 / Import",(d,w)->{
                    if(new WorkflowStore(this).stage(json))finish();else failure("Could not save draft.");
                }).setOnCancelListener(d->finish()).show();return;
        }
        if (deployment) {
            DeploymentSkill skill=DeploymentCodec.decode(json);
            new AlertDialog.Builder(this).setTitle("Import workflow deployment draft?")
                    .setMessage("Source demo: "+skill.source.appPackage+"\nTarget: "+skill.targetPackage+"\n"
                            +skill.roles.get(0)+" → "+skill.targetIds.get(0)+"\n"+skill.roles.get(1)+" → "+skill.targetIds.get(1)
                            +"\nNo approval is transferred. Check current bindings and confirm their meaning before running.")
                    .setNegativeButton("Cancel",(d,w)->finish()).setPositiveButton("Import draft",(d,w)-> {
                        try {if(new DeploymentStore(this).importDraft(json))finish();else failure("Draft could not be saved.");}
                        catch(IllegalArgumentException error) {failure("Version conflicts with reviewed history. Existing skills are unchanged.");}
                    }).setOnCancelListener(d->finish()).show();
            return;
        }
        if (twoStep) {
            TwoStepSkill skill=TwoStepCodec.decode(json);
            new AlertDialog.Builder(this).setTitle("Import two-step draft?")
                    .setMessage(skill.appPackage+"\n"+skill.steps.get(0).resourceId+"\n"+skill.steps.get(1).resourceId
                            +"\nSource claims only. Nothing will run. Existing approvals remain unchanged. Check both bindings, then review and save.")
                    .setNegativeButton("Cancel",(d,w)->finish()).setPositiveButton("Import draft",(d,w)-> {
                        if(new TwoStepStore(this).importDraft(json)) finish();else failure("Draft could not be saved.");
                    }).setOnCancelListener(d->finish()).show();
            return;
        }
        SwitchSkill skill = SkillCodec.decode(json);
        new AlertDialog.Builder(this).setTitle("Import as an unreviewed draft?")
                .setMessage(skill.appPackage + "\n" + skill.resourceId
                        + "\nSET_CHECKED(desired: boolean)\nThe file claims a demonstration; this device has not verified it."
                        + "\nNo action will run. Your reviewed skill remains active until you explicitly replace it."
                        + "\nNext: select this app, check binding, then review and save.")
                .setNegativeButton("Cancel", (d, w) -> finish())
                .setPositiveButton("Import draft", (d, w) -> {
                    if (new SkillStore(this).importDraft(json)) finish(); else failure("Draft could not be saved.");
                }).setOnCancelListener(d -> finish()).show();
    }
    private void failure(String text) {
        String shown=en?text:text.startsWith("No reviewed")?"尚无已审核技能可以导出。":text.contains("timed out")?"文件操作超时，没有导入技能。导出的文件可能不完整，请检查后重试。":text.contains("interrupted")?"文件处理被中断。没有新增审批，请重新选择文件。":"文件未能处理，已有技能不变。请检查文件内容和访问权限后重试。";
        message.setText(shown);
        new AlertDialog.Builder(this).setTitle(t("技能文件未完成","Skill file not completed")).setMessage(shown)
                .setPositiveButton(t("关闭","Close"), (d, w) -> finish()).setOnCancelListener(d -> finish()).show();
    }
    @Override protected void onDestroy() {
        finished = true; generation++; handler.removeCallbacksAndMessages(null);
        if (signal != null) signal.cancel(); worker.shutdownNow(); super.onDestroy();
    }
}
