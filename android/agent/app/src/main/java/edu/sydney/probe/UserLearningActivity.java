package edu.sydney.probe;
import android.app.*;
import android.content.*;
import android.os.*;
import android.widget.*;
import org.json.*;

/** Ordinary assisted-learning entry. Drafts are NOT formal knowledge or execution permission. */
public final class UserLearningActivity extends Activity {
    private boolean en,busy,legacy;private long ticket;private String currentId="",pendingGeneration="";
    private TextView status;private EditText goal,document,name;private Spinner scope;
    private CheckBox useRecording;
    private UserLearningClient client;private final Handler handler=new Handler(Looper.getMainLooper());
    private String t(String zh,String english){return en?english:zh;}
    private String uid(){return java.util.UUID.randomUUID().toString().replace("-","");}
    private int id(String key){return getResources().getIdentifier(key,"id",getPackageName());}
    @Override public void onCreate(Bundle saved){super.onCreate(saved);en=getSharedPreferences("language_connection",0).getBoolean("english",false);legacy=getIntent().getBooleanExtra("legacy",false);currentId=getPreferences(0).getString("candidate_id","");pendingGeneration=currentId;draw();
        if(saved!=null){goal.setText(saved.getString("goal",""));document.setText(saved.getString("document",""));name.setText(saved.getString("name",""));scope.setSelection(saved.getInt("scope",0));useRecording.setChecked(saved.getBoolean("use_recording",false));}}
    private EditText field(LinearLayout page,String key,String hint){var v=new EditText(this);v.setId(id(key));v.setHint(hint);Ui.field(v);page.addView(v);return v;}
    private void draw(){
        var page=Ui.page(this);Ui.toolbar(page,t("学习一个新流程","Learn a new Flow"),"learningLanguage",en?"中文":"English",()->{
            if(busy||UserLearningSession.active()){show(t("请先停止当前录制或生成。","Stop recording or generation first."));return;}
            String g=goal.getText().toString(),d=document.getText().toString(),n=name.getText().toString();int p=scope.getSelectedItemPosition();boolean included=useRecording.isChecked();
            en=!en;getSharedPreferences("language_connection",0).edit().putBoolean("english",en).apply();draw();goal.setText(g);document.setText(d);name.setText(n);scope.setSelection(p);useRecording.setChecked(included);
        },"learningBack",t("返回","Back"),()->{cancel();finish();});
        Ui.label(page,t("材料 → 模型草稿 → 检查 → 实测 → 发布","Material → draft → check → validate → publish"),18);
        Ui.label(page,t("当前入口支持示范/资料辅助，不是任意 App 自动学习。生成和保存草稿不会操作业务或授予执行权限。","Demonstration/document assisted; not arbitrary App learning. Generating or saving a draft does not execute business actions or grant rights."),14);
        Ui.action(page,"learningConnection",t("检查实际连接状态","Check connection state"),()->rpc(uid(),"status",new JSONObject()),false);
        goal=field(page,"learningGoal",t("要学习什么？请写目标和必须保持的属性","What should be learned? Include the goal and properties to preserve."));
        scope=new Spinner(this);scope.setId(id("learningScope"));scope.setAdapter(new ArrayAdapter<String>(this,android.R.layout.simple_spinner_dropdown_item,new String[]{"Parameter Room · edu.sydney.parameterroom","Transfer Bench · edu.sydney.transferlab"}));page.addView(scope);
        Ui.label(page,t("录制只采集所选实验 App 的无障碍树和被动事件，不截屏。操作者由你声明，事件归因仍可能 UNKNOWN。最长120秒/64次观察；离开范围停止。返回此页即结束。","Only this experiment App's accessibility trees and passive events; no screenshot. Actor is user-declared and may remain UNKNOWN. Max 120s/64 observations. Leaving scope stops capture; returning here ends it."),14);
        Ui.action(page,"learningStart",t("开始示范并打开所选 App","Start demonstration & open App"),this::record,true);
        Ui.action(page,"learningStop",t("结束录制 / 查看材料","Stop recording / inspect material"),()->{try{if(UserLearningSession.active())UserLearningSession.finish(false);materialStatus();}catch(Exception e){error(e);}},false);
        document=field(page,"learningDocument",t("可选：粘贴公开操作说明（不要放密码或密钥）","Optional public instructions (no password or key)"));
        useRecording=new CheckBox(this);useRecording.setId(id("learningUseRecording"));useRecording.setText(t("附上本次新录制材料","Include the new recording material"));page.addView(useRecording);
        if(legacy){scope.setSelection(1);try(var f=openFileInput("workflow-trace.json")){goal.setText(new JSONObject(SkillFiles.read(f,262144)).optString("goal",""));}catch(Exception e){error(e);}}
        if(legacy)Ui.label(page,t("已选择旧录制：它只作为来源片段，不冒充完整页面记忆或已验证动作。","Legacy recording selected: source fragment only, not complete page memory or verified actions."),14);
        Ui.action(page,"learningGenerate",t("核对上传内容并生成草稿","Review upload & generate draft"),this::generate,true);
        name=field(page,"learningName",t("草稿名称（名称不是 Flow ID）","Draft name (not Flow ID)"));
        Ui.action(page,"learningSave",t("命名并保存草稿","Name & save draft"),()->{if(currentId.isEmpty()){show(t("请先生成候选。","Generate a candidate first."));return;}try{rpc(currentId,"name",new JSONObject().put("name",name.getText().toString()));}catch(Exception e){error(e);}},false);
        Ui.action(page,"learningReload",t("重载上次草稿","Reload last draft"),()->{if(!currentId.isEmpty())rpc(currentId,"inspect",new JSONObject());else show(t("没有已登记的草稿。","No saved candidate ID."));},false);
        Ui.action(page,"learningValidate",t("检查参数、实测与发布","Check parameters, validate & publish"),()->{if(!idle()){show("BUSY");return;}if(!currentId.matches("[a-f0-9]{32}")){show(t("请先生成草稿。","Generate a draft first."));return;}startActivity(new Intent(this,UserCandidateActivity.class).putExtra("candidate_id",currentId));},false);
        Ui.label(page,t("格式检查不等于实测。未知项必须解决；确认实测后，只有真实核验通过的候选才能发布。","Format checks are not device validation. Resolve unknowns first; only genuinely verified candidates may publish."),14);
        Ui.action(page,"learningCancel",t("取消当前生成 / 停止采集","Cancel generation / stop capture"),this::cancel,false);
        status=Ui.label(page,"",14);status.setId(id("learningStatus"));Ui.notice(status);status.setAccessibilityLiveRegion(android.view.View.ACCESSIBILITY_LIVE_REGION_POLITE);materialStatus();
    }
    private boolean idle(){var s=ProbeService.current();return !busy&&!UserLearningSession.active()&&(s==null||(!s.workflowRunning()&&!s.workflowPreparing()&&!s.isRecording()));}
    private String pkg(){return scope.getSelectedItemPosition()==0?"edu.sydney.parameterroom":"edu.sydney.transferlab";}
    private void record(){if(!idle()){show("BUSY");return;}try{
        String target=pkg();var intent=getPackageManager().getLaunchIntentForPackage(target);if(intent==null)throw new IllegalStateException("APP_NOT_INSTALLED");
        UserLearningSession.start(this,target,goal.getText().toString());useRecording.setChecked(true);startActivity(intent);
    }catch(Exception e){try{if(UserLearningSession.active())UserLearningSession.finish(true);}catch(Exception ignored){}error(e);}}
    private JSONObject payload()throws Exception{
        String target=pkg();var observations=new JSONArray();Object events=JSONObject.NULL,trace=JSONObject.NULL;
        if(useRecording.isChecked()){var recorded=UserLearningSession.read(this);
            if(!target.equals(recorded.getString("app_package")))throw new IllegalArgumentException("RECORDING_SCOPE_CHANGED");
            if(!"STOPPED".equals(recorded.getString("state")))throw new IllegalArgumentException("RECORDING_INCOMPLETE");
            if(!goal.getText().toString().equals(recorded.getString("goal")))throw new IllegalArgumentException("RECORDING_GOAL_CHANGED");
            observations=recorded.getJSONArray("observations");events=recorded.opt("events");if(events==null)events=JSONObject.NULL;
        }
        if(legacy){try(var f=openFileInput("workflow-trace.json")){trace=new JSONObject(SkillFiles.read(f,262144));}}
        var environment=new JSONObject().put("app_package",target).put("app_build",String.valueOf(getPackageManager().getPackageInfo(target,0).getLongVersionCode()))
            .put("environment_id",target.equals("edu.sydney.parameterroom")?"parameter-room-u0":"transfer-u0").put("ui_revision","ui.u0").put("domain","EXPERIMENT_APP");
        return new JSONObject().put("goal",SemanticParameterCodec.text(goal.getText().toString(),2000)).put("environment",environment).put("observations",observations)
            .put("events",events).put("legacy_trace",trace).put("document",document.getText().toString()).put("upload_confirmed",true);
    }
    private void generate(){if(!idle()){show("BUSY");return;}if(!pendingGeneration.isEmpty()){show(t("请先重载或取消上次请求，不能重发未确认的生成。","Reload or cancel the previous request before generating again."));return;}try{
        final JSONObject raw=payload();final long generation=++ticket;
        new AlertDialog.Builder(this).setTitle(t("确认向模型上传","Confirm model upload"))
            .setMessage(t("上传任务说明、公开树摘要、被动事件/旧录制片段和你填写的资料。敏感内容按管线脱敏；不会发送密钥或隐藏评测答案。最多2次请求、120秒，无网络自动重试。仅生成草稿，不执行。","Uploads task, public tree summaries, passive/legacy fragments and your document. Pipeline redaction applies; no keys or hidden test answers. Max 2 requests/120s, no network retry. Draft only; no execution.")+"\n"+t("观察数：","Observations: ")+raw.getJSONArray("observations").length()+"\n"+t("资料字符：","Document characters: ")+raw.getString("document").length())
            .setNegativeButton(t("取消","Cancel"),null).setPositiveButton(t("确认生成","Generate"),(d,w)->{
                try{if(generation!=ticket||!idle()||!raw.toString().equals(payload().toString()))throw new IllegalStateException("STALE_CONFIRMATION");
                    currentId=uid();getPreferences(0).edit().putString("candidate_id",currentId).commit();pendingGeneration=currentId;rpc(currentId,"generate",raw);
                }catch(Exception e){error(e);}
            }).show();
    }catch(Exception e){error(e);}}
    private void rpc(String id,String operation,JSONObject payload){
        if(busy){show("BUSY");return;}busy=true;long generation=++ticket;client=new UserLearningClient();var active=client;
        String pairing=getSharedPreferences("language_connection",0).getString("pairing","");show(t("正在请求；尚未执行业务…","Requesting; no business actions…"));
        active.start(id,operation,payload,pairing,(result,failure)->handler.post(()->{
            if(generation!=ticket||isDestroyed())return;busy=false;client=null;if(operation.equals("generate")&&failure==null)pendingGeneration="";
            if(failure!=null){error(failure);return;}try{
                if(operation.equals("status")){show(ProbeService.connectionAudit().toString(2)+"\n"+result.toString(2)+"\n"+t("网关可达不等于模型 API 已实测可用。","Reachable gateway does not prove usable model API."));return;}
                StringBuilder summary=new StringBuilder(result.optString("state","UNKNOWN"));summary.append("\nID: ").append(result.optString("id"));
                if(operation.equals("inspect")&&!result.optString("state").equals("GENERATING"))pendingGeneration="";
                summary.append("\n").append(t("名称：","Name: ")).append(result.optString("name",""));
                var body=result.optJSONObject("body");var g=body==null?null:body.optJSONObject("generation");
                if(g!=null&&g.isNull("candidate_flow")){summary.append("\n").append(t("需要补充资料：","More material needed: ")).append(g.opt("questions")).append("\n").append(g.opt("uncertainties"));}
                else if(g!=null){var flow=g.getJSONObject("candidate_flow");summary.append("\n").append(flow.getString("id")).append(" @ ").append(flow.getString("version"))
                    .append("\n").append(t("参数：","Inputs: ")).append(flow.getJSONArray("inputs").toString(2))
                    .append("\n").append(t("待确认：","Unknowns: ")).append(g.opt("knowledge_gaps")).append("\n").append(g.opt("uncertainties"))
                    .append("\n").append(t("内容检查：","Content checks: ")).append(g.opt("content_analysis"))
                    .append("\nPROGRAM_NORMALIZATION: ").append(g.getJSONObject("program_normalization").getJSONArray("diff").toString(2));}
                summary.append("\n").append(t("未实测 · 未发布 · 无执行权限","Not device-validated · not published · no execution rights"));show(summary.toString());
            }catch(Exception e){error(e);}
        }));
    }
    private void cancel(){
        final long generation=++ticket;if(client!=null)client.cancel();client=null;busy=false;
        String id=pendingGeneration;pendingGeneration="";
        if(!id.isEmpty())new UserLearningClient().start(id,"cancel",new JSONObject(),getSharedPreferences("language_connection",0).getString("pairing",""),(result,error)->handler.post(()->{
            if(generation==ticket&&!isDestroyed())show(error==null?t("服务器已收到取消。已发出的模型请求可能仍计费，但结果不能恢复执行权。","Server cancellation recorded. Sent requests may still cost; no execution rights are restored."):t("本机已停止接收；服务器取消未确认。草稿没有执行权。","Local callbacks blocked; server cancellation unconfirmed. Drafts have no execution rights."));
        }));
        try{if(UserLearningSession.active())UserLearningSession.finish(true);}catch(Exception e){error(e);}
        show(t("本机已取消；不自动重做。","Cancelled locally; no automatic retry."));
    }
    private void materialStatus(){try{var r=UserLearningSession.read(this);show(t("录制状态：","Recording state: ")+r.getString("state")+"\n"+t("观察数：","Observations: ")+r.getJSONArray("observations").length()+"\n"+t("采集问题：","Capture issue: ")+r.opt("last_capture_error")+"\n"+t("页面实体可能 UNKNOWN；材料不是执行授权。","Entity may be UNKNOWN; material is not execution authority."));}catch(Exception e){show(t("尚无新录制。可以开始示范或提供公开说明。","No new recording. Demonstrate or provide public instructions."));}}
    private void show(String value){if(status!=null)status.setText(value);}
    private void error(Exception e){show("UNCONFIRMED / "+String.valueOf(e.getMessage()));}
    @Override protected void onResume(){super.onResume();try{if(UserLearningSession.active())UserLearningSession.finish(false);}catch(Exception e){error(e);}if(status!=null&&!busy)materialStatus();}
    @Override protected void onPause(){if(busy)cancel();super.onPause();}
    @Override protected void onSaveInstanceState(Bundle out){super.onSaveInstanceState(out);out.putString("goal",goal.getText().toString());out.putString("document",document.getText().toString());out.putString("name",name.getText().toString());out.putInt("scope",scope.getSelectedItemPosition());out.putBoolean("use_recording",useRecording.isChecked());}
    @Override protected void onDestroy(){handler.removeCallbacksAndMessages(null);super.onDestroy();}
}
