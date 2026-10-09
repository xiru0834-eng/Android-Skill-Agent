package edu.sydney.probe;

import android.app.*;
import android.content.*;
import android.os.*;
import android.provider.Settings;
import android.text.InputFilter;
import android.view.View;
import android.widget.*;
import org.json.*;

/** End-user journey; the existing experimental workbench and replay rules remain intact. */
public final class TeachingActivity extends Activity {
    private LinearLayout column,preparation,review,library,header,recordSummary,tools;
    private EditText name,goal,pairing;
    private TextView status,guide,guideHint,savedInfo,stateTitle,stateHint,progress,recordActions;
    private TextView[] stageViews;
    private ScrollView guideScroll;
    private Button record,stop,cancel,generate,save,run,restart,resume,runStop;
    private SharedPreferences prefs;
    private final Handler handler=new Handler(Looper.getMainLooper());
    private final TeachingGuard guard=new TeachingGuard();
    private boolean en,busy,startPrompt,draftStorageUnconfirmed;
    private String message="";
    private final Runnable poll=new Runnable(){public void run(){refresh();handler.postDelayed(this,700);}};
    private String t(String zh,String english){return en?english:zh;}
    @Override public void onCreate(Bundle state){super.onCreate(state);prefs=getSharedPreferences("teaching_journey",0);en=getSharedPreferences("language_connection",0).getBoolean("english",false);draw();}
    private void draw() {
        Ui.configure(this);LinearLayout frame=Ui.column(this);frame.setGravity(android.view.Gravity.CENTER_HORIZONTAL);frame.setBackgroundColor(UiStyle.BACKGROUND);setContentView(frame);
        LinearLayout root=Ui.column(this);frame.addView(root,new LinearLayout.LayoutParams(Math.min(getResources().getDisplayMetrics().widthPixels,dp(640)),-1));
        column=new LinearLayout(this);column.setOrientation(1);column.setPadding(dp(20),dp(8),dp(20),dp(12));root.addView(column);
        Ui.toolbar(column,t("录制新流程","Teach a routine"),"teachLanguage",en?"中文":"English",()->{persistInputs();en=!en;getSharedPreferences("language_connection",0).edit().putBoolean("english",en).apply();draw();},"teachBack",t("返回首页","Back to home"),this::finish);
        stageViews=Ui.stages(column,en);
        if(getIntent().getBooleanExtra("automatedTest",false))text(t("自动化测试模式：记录不计为真人示范。","AUTOMATED TEST: not a human demonstration."),16);
        header=group();header.setPadding(dp(16),dp(10),dp(16),dp(10));stateTitle=text("",18);stateTitle.setId(id("teachStateTitle"));stateTitle.setAccessibilityLiveRegion(View.ACCESSIBILITY_LIVE_REGION_POLITE);
        stateHint=text("",14);stateHint.setId(id("teachStateHint"));status=text("",14);status.setId(id("teachStatus"));
        ScrollView scroll=new ScrollView(this);root.addView(scroll,new LinearLayout.LayoutParams(-1,0,1));column=new LinearLayout(this);column.setOrientation(1);column.setPadding(dp(20),0,dp(20),dp(24));scroll.addView(column);
        LinearLayout body=column;
        progress=text("",16);progress.setId(id("teachProgress"));
        resume=button("teachResume",t("返回实验界面，继续操作","Return to experiment"),()->{ProbeService s=ProbeService.current();if(s!=null&&s.workflowRecorder().active()){openTarget();s.teachingControls().show(true);}});
        stop=button("teachStop",t("结束录制","Finish recording"),()->stop(false));
        cancel=button("teachCancel",t("取消本次录制","Cancel recording"),()->new AlertDialog.Builder(this).setTitle(t("取消这次录制？","Cancel this recording?"))
            .setMessage(t("已有记录会保留，但不会生成技能。","Evidence is kept, but no skill will be generated."))
            .setNegativeButton(t("继续录制","Keep recording"),null).setPositiveButton(t("取消录制","Cancel recording"),(d,w)->stop(true)).show());
        Ui.pair(body,stop,cancel);
        preparation=Ui.panel(body);column=preparation;text(t("这次想教什么？","What routine will you teach?"),20);
        text(t("技能名称","Skill name"),16);name=input("teachName",prefs.getString("name",t("阅读模式","Reading mode")),60);
        text(t("任务目标（中文或英文）","Goal (Chinese or English)"),16);
        goal=input("teachGoal",prefs.getString("goal",t("打开阅读灯，亮度设为60%，打开风扇并设为低档。","Turn on the reading lamp at 60% and turn on the fan at low speed.")),240);
        name.setSingleLine(true);goal.setMinLines(2);goal.setMaxLines(4);
        record=button("teachRecord",t("开始录制","Start recording"),this::startRecording);primary(record);
        Button instructions=button("teachInstructions",t("查看示范步骤","How to demonstrate"),()->dialog(t("这版能录什么","Supported demonstration"),t("单页和跨页都可录，不要求固定步数或灯/风扇固定组合。\n\n可以只调亮度、只开关电源，也可以分次保存、取消修改、重复进入页面、先开再关。\n\n从已保存的总览或单页开始。等“正在录制”再操作；每次点击等确认。完成后保存修改，回到总览或留在单页，点“结束录制”。\n\n未涉及字段保持执行开始时的值。指南保留操作顺序；不能只凭最后数值就认定中间过程完成。当前只支持实验 App 的已定义控件，不是任意 App 录制器。","Single-page and cross-page workflows are supported, without a fixed step count or mandatory device group.\n\nAdjust only brightness or power; save in stages, cancel edits, revisit pages, or turn on then off.\n\nStart at a saved overview or single page. Wait for Recording and confirmation after each tap. Save changes, finish at overview or single page, then tap Finish recording.\n\nUntouched fields keep execution-start values. The guide retains action order, not just the final values. Only defined controls in the experiment App are supported.")));Ui.quiet(instructions);
        column=body;recordSummary=Ui.panel(body);column=recordSummary;text(t("已记录的操作","Recorded actions"),20);
        text(t("来自本机确认的记录，尚未保存为技能。","Locally confirmed evidence. Not a saved skill yet."),14);
        recordActions=text("",16);recordActions.setId(id("teachRecordedActions"));
        column=body;review=Ui.panel(body);column=review;text(t("核对操作指南","Review the guide"),20);
        text(t("按实际记录在本机整理。核对每一步后再保存，不会自动执行。旧格式仍需配对电脑。","Compiled locally from the recording. Check every step before saving; nothing runs automatically. Legacy records still need the paired computer."),14);
        generate=button("teachGenerate",t("整理操作指南","Generate a guide"),this::generate);
        primary(generate);
        guideScroll=new ScrollView(this);guideScroll.setId(id("teachGuideScroll"));guideScroll.setFillViewport(true);
        int heightDp=Math.round(getResources().getDisplayMetrics().heightPixels/getResources().getDisplayMetrics().density);
        guideScroll.setNestedScrollingEnabled(true);guideScroll.setOnTouchListener((v,event)->{v.getParent().requestDisallowInterceptTouchEvent(event.getActionMasked()!=android.view.MotionEvent.ACTION_UP&&event.getActionMasked()!=android.view.MotionEvent.ACTION_CANCEL);return false;});
        review.addView(guideScroll,new LinearLayout.LayoutParams(-1,dp(UiPresentation.guideHeightDp(heightDp))));
        LinearLayout guideBody=Ui.column(this);guideBody.setPadding(dp(4),dp(8),dp(4),dp(8));guideScroll.addView(guideBody);
        guide=Ui.label(guideBody,"",16);guide.setId(id("teachGuide"));
        guideHint=text(t("可上下滚动，核对全部步骤。","Scroll through and check every recorded step."),14);
        save=button("teachSave",t("核对无误，保存技能","Review & save skill"),this::save);
        primary(save);column=body;
        restart=button("teachNew",t("重新录制","Record again"),()->{persistInputs();prefs.edit().remove("currentTrace").apply();message="";draw();});
        Button toolsToggle=button("teachTools",t("帮助与设置  ＋","Help & settings  ＋"),()->{});
        Ui.quiet(toolsToggle);
        tools=Ui.column(this);body.addView(tools);tools.setVisibility(View.GONE);toolsToggle.setOnClickListener(v->{boolean show=tools.getVisibility()!=View.VISIBLE;tools.setVisibility(show?View.VISIBLE:View.GONE);toolsToggle.setText(show?t("收起帮助与设置  −","Hide help & settings  −"):t("帮助与设置  ＋","Help & settings  ＋"));});
        column=tools;
        button("teachDetails",t("记录与运行详情","Recording & run details"),()->{
            try{JSONObject tr=new JSONObject(trace());StringBuilder detail=new StringBuilder(TeachingText.recordOrigin(tr.optString("source"),en)).append("\n").append(TeachingText.recordState(tr.optString("end"),en));
                JSONArray steps=tr.getJSONArray("steps");detail.append(t("\n已记录：","\nRecorded: ")).append(steps.length()).append("\n");
                for(int i=0;i<steps.length();i++)detail.append(i+1).append(". ").append(steps.getJSONObject(i).optString("id")).append('\n');
                detail.append("\n").append(TeachingRecordView.actions(tr,en)).append("\nTrace: ").append(tr.optString("traceId")).append("\nCode: ").append(tr.optString("error")).append("\nLast run: ").append(new WorkflowStore(this).result());dialog(t("最近一份记录（可能是历史记录）","Latest record (may be historical)"),detail.toString());
            }catch(Exception e){dialog(t("记录详情","Recording details"),t("暂无记录。","No record yet."));}});
        button("teachSetup",t("无障碍服务设置","Accessibility settings"),()->startActivity(new Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS)));
        button("teachResources",t("录制与执行资源预算","Recording / execution budgets"),()->WorkflowResourceDialog.show(this,!data().active&&!data().running&&!busy,en,this::refresh));
        button("teachConnection",t("电脑配对设置","Computer pairing"),()->pairing.setVisibility(pairing.getVisibility()==View.VISIBLE?View.GONE:View.VISIBLE));
        pairing=input("teachPairing",getSharedPreferences("language_connection",0).getString("pairing",""),48);pairing.setInputType(129);pairing.setHint(t("配对码，不是 API Key","Pairing code, not API key"));pairing.setVisibility(View.GONE);
        column=body;
        Button savedToggle=button("teachLibraryToggle",t("查看已保存技能  ＋","Saved routine  ＋"),()->library.setVisibility(library.getVisibility()==View.VISIBLE?View.GONE:View.VISIBLE));Ui.quiet(savedToggle);
        library=Ui.panel(body);column=library;text(t("已保存技能","Saved skill"),20);
        savedInfo=text("",16);savedInfo.setId(id("teachSaved"));
        button("teachView",t("查看已保存的操作指南","View saved guide"),()->{String raw=new WorkflowStore(this).approved();if(raw==null)dialog(t("还没有技能","No saved skill"),t("先完成示范和审核。","Complete a demonstration and review first."));else dialog(new WorkflowStore(this).name(),TeachingGuide.render(raw,en,WorkflowResourceStore.read(this)));});
        run=button("teachRun",t("执行已保存的技能","Run saved skill"),this::run);
        runStop=button("teachRunStop",t("停止执行","Stop execution"),()->{ProbeService s=ProbeService.current();if(s!=null)s.stopAll();refresh();});
        button("namedLibrary",t("查看全部技能 / 输入指令","All skills / Enter a command"),()->startActivity(new Intent(this,WorkflowLibraryActivity.class)));
        text(t("旧技能保留。保存不代表跨设备验证通过。","Existing skills are kept. Saved does not mean cross-device verified."),14);
        library.setVisibility(getIntent().getBooleanExtra("library",false)?View.VISIBLE:View.GONE);column=body;
        text(t("只录制 Transfer Bench 实验 App，不操作真实家电。","Transfer Bench experiment only. No real appliances."),14);
        refresh();
        if(getIntent().getBooleanExtra("pairingSetup",false)){
            tools.setVisibility(View.VISIBLE);pairing.setVisibility(View.VISIBLE);
            toolsToggle.setText(t("收起帮助与设置  −","Hide help & settings  −"));
            scroll.post(()->scroll.scrollTo(0,tools.getTop()));
        }
    }
    private void persistInputs(){if(name!=null)prefs.edit().putString("name",name.getText().toString()).putString("goal",goal.getText().toString()).apply();}
    private String trace(){try(java.io.InputStream in=openFileInput("workflow-trace.json")){byte[] b=in.readNBytes(262145);if(b.length>262144)return null;return new String(b,java.nio.charset.StandardCharsets.UTF_8);}catch(Exception e){return null;}}
    private void startRecording() {
        if(startPrompt||busy)return;persistInputs();
        final String checkedGoal;
        try{TeachingInput.name(name.getText().toString());checkedGoal=TeachingInput.goal(goal.getText().toString());}
        catch(IllegalArgumentException e){message=metadataError(e);refresh();return;}
        ProbeService s=ProbeService.current();
        if(s==null){message=t("请先开启无障碍服务。","Enable the accessibility service first.");refresh();return;}
        if(name.getText().toString().isBlank()||goal.getText().toString().isBlank()){message=t("请填写名称和任务目标。","Enter a name and goal.");refresh();return;}
        if(!TeachingStatus.canStart(data()))return;
        startPrompt=true;WorkflowResources resources=WorkflowResourceStore.read(this);
        AlertDialog prompt=new AlertDialog.Builder(this).setTitle(t("开始新的示范？","Start a new demonstration?"))
            .setMessage(t("先打开实验 App 检查准备状态（最多60秒），还不会录制。有旧修改时，请你自己保存或取消；Single 中灯和风扇分别保存。保持想录的单页或三页，点准备浮条上的“开始录制”，看到“正在录制”后再示范。\n每次点击等确认；完成后保存修改，在单页或总览点“结束录制”。已有技能不变，未涉及字段保持执行初态。","First check the experiment (up to 60 seconds); recording has NOT started. Save or cancel old edits yourself; in Single, save lamp and fan separately. Keep your chosen layout and tap Start recording on the preparation bar. Wait for Recording before demonstrating.\nWait for confirmation after each action, save changes, then finish at single page or overview. Existing skills stay unchanged; untouched fields keep execution-start values.")+t("\n当前录制预算：","\nRecording budget: ")+resources.recordingMinutes+t(" 分钟；每步确认："," minutes; confirmation: ")+resources.confirmationSeconds+t(" 秒。可在帮助与设置里调整，运行中不延长。"," seconds. Adjust under Help & settings; running deadlines cannot be extended."))
            .setNegativeButton(t("取消","Cancel"),null).setPositiveButton(t("开始","Start"),(d,w)->{
                try{if(!TeachingStatus.canStart(data()))return;TeachingInput.name(name.getText().toString());if(!checkedGoal.equals(TeachingInput.goal(goal.getText().toString())))throw new IllegalArgumentException("GOAL_CHANGED");guard.cancel();prefs.edit().remove("draft").remove("draftTrace").apply();s.prepareRecording(checkedGoal,getIntent().getBooleanExtra("automatedTest",false)?"AUTOMATED":"HUMAN_DECLARED");message=t("请先在准备浮条检查状态，再点开始录制。","Check the preparation bar, then tap Start recording.");}
                catch(Exception e){s.workflowRecorder().stop("INTERRUPTED");message=t("未能开始，请检查实验 App 和服务。","Could not start. Check the experimental App and service.");}refresh();}).create();
        prompt.setOnDismissListener(d->startPrompt=false);prompt.show();
    }
    private void stop(boolean cancelled){ProbeService s=ProbeService.current();if(s!=null){if(!cancelled&&s.workflowRecorder().active()&&(!s.workflowRecorder().ready()||s.workflowRecorder().hasPending()))return;if(cancelled)s.workflowRecorder().stop("CANCELLED");s.stopAll();}guard.cancel();message="";refresh();}
    private void generate() {
        if(busy||!TeachingStatus.canGenerate(TeachingStatus.kind(data())))return;persistInputs();String raw=trace();
        try{JSONObject tr=new JSONObject(raw);if(tr.optInt("version")==2){
            JSONObject skill=FlexibleWorkflowCodec.compile(raw);
            if(!saveDraft(skill.toString(),raw))throw new IllegalStateException("DRAFT_STORAGE_UNCONFIRMED");
            message=t("指南已按实际记录在本地整理，未调用 GPT。请核对目标和每一步，再保存。","Guide compiled locally from the recording; GPT was not called. Check the goal and each step, then save.");refresh();return;
        }}catch(Exception e){message=t("记录未通过完整性检查：","Recording check failed: ")+e.getMessage();refresh();return;}
        try{JSONObject tr=new JSONObject(raw);if(!tr.getString("end").equals("STOPPED")||!tr.getString("error").isEmpty()||!TeachingRoute.complete(TeachingRecordView.ids(tr)))throw new IllegalArgumentException();}
        catch(Exception e){message=t("需要完整且已结束的一组四步或两组八步示范。不会自动补步骤。","A complete stopped four-step or eight-step demonstration is required. Missing actions will not be invented.");refresh();return;}
        String token=pairing.getText().toString().trim();
        if(!token.matches("[a-f0-9]{48}")){tools.setVisibility(View.VISIBLE);pairing.setVisibility(View.VISIBLE);message=t("先填写电脑配对码并启动 USB 网关，不是 API Key。","Set the pairing code and start the USB bridge, not an API key.");refresh();return;}
        getSharedPreferences("language_connection",0).edit().putString("pairing",token).apply();
        long ticket=guard.begin(raw);busy=true;message=t("正在整理，请稍候；尚未保存技能。","Generating; nothing has been saved yet.");prefs.edit().remove("draft").remove("draftTrace").apply();refresh();
        new Thread(()->{try{JSONObject result=TeachingClient.request(raw,token);handler.post(()->{
            if(isDestroyed()||!guard.accepts(ticket,trace())){busy=false;return;}
            busy=false;try{if(result.getString("status").equals("candidate")){if(!saveDraft(result.getJSONObject("skill").toString(),raw))throw new IllegalStateException("DRAFT_STORAGE_UNCONFIRMED");message=t("指南已生成，请逐步核对后保存。","Guide ready. Review each step before saving.");}else message=t("尚不能保存，请检查目标并重新示范：","Not ready to save. Check the goal and record again: ")+result.getString("reason");}catch(Exception e){message=t("返回内容或草稿存储未确认：","Response or draft storage unconfirmed: ")+e.getMessage();}refresh();});}
            catch(Exception e){handler.post(()->{if(isDestroyed())return;busy=false;message=t("整理失败，记录已保留。检查电脑连接后重试。错误：","Generation failed; recording kept. Check the computer connection and retry. Code: ")+e.getClass().getSimpleName()+(e instanceof IllegalArgumentException?" / "+e.getMessage():"");refresh();});}},"teaching-compile").start();
    }
    private boolean selected(JSONObject tr){return !prefs.getString("currentTrace","").isEmpty()&&prefs.getString("currentTrace","").equals(tr.optString("traceId"));}
    private boolean saveDraft(String raw,String evidence){draftStorageUnconfirmed=!prefs.edit().putString("draft",raw).putString("draftTrace",evidence).commit();return !draftStorageUnconfirmed;}
    private String draft(){if(draftStorageUnconfirmed)return null;try{if(!selected(new JSONObject(trace())))return null;}catch(Exception e){return null;}String raw=prefs.getString("draft",null);return raw!=null&&prefs.getString("draftTrace","").equals(trace())?raw:null;}
    private void save(){String raw=draft();if(raw==null||busy)return;persistInputs();final String title;
        try{title=TeachingInput.name(name.getText().toString());}catch(IllegalArgumentException e){message=metadataError(e);refresh();return;}
        EditText saveName=new EditText(this);saveName.setId(id("teachSaveName"));saveName.setText(title);saveName.setHint(t("技能名称（最多60个字符，不能重名）","Unique skill name (maximum 60 UTF-16 units)"));
        LinearLayout reviewBody=Ui.column(this);reviewBody.setPadding(dp(16),dp(8),dp(16),dp(8));
        Ui.field(saveName);reviewBody.addView(saveName);
        ScrollView guideScroll=new ScrollView(this);LinearLayout guideBody=Ui.column(this);guideScroll.addView(guideBody);
        Ui.label(guideBody,title+"\n"+TeachingGuide.render(raw,en,WorkflowResourceStore.read(this))+t("\n\n加入我的技能；旧技能保留，不会自动执行。","\n\nAdds to My skills; previous skills are kept. Does not execute."),16);
        android.graphics.Rect available=new android.graphics.Rect();getWindow().getDecorView().getWindowVisibleDisplayFrame(available);
        reviewBody.addView(guideScroll,new LinearLayout.LayoutParams(-1,ReviewLayout.guideHeightPx(available.height(),getResources().getDisplayMetrics().density)));
        new AlertDialog.Builder(this).setTitle(t("确认保存这份指南？","Save this reviewed guide?"))
            .setView(reviewBody)
            .setNegativeButton(t("返回检查","Back"),null).setPositiveButton(t("确认保存","Save"),(d,w)->{final String chosen;
                try{chosen=TeachingInput.name(saveName.getText().toString());}catch(IllegalArgumentException e){message=metadataError(e);refresh();return;}
                WorkflowStore store=new WorkflowStore(this);if(raw.equals(draft())&&store.reviewCompiled(raw,chosen)){name.setText(chosen);persistInputs();message=t("技能已保存，可以查看或主动执行。","Skill saved. View it or choose Run.");}else message=store.storageUnconfirmed()?t("保存持久性未确认，已禁止执行。请检查存储并重新审核，不代表旧技能已丢失。","Save persistence unconfirmed; execution is blocked. Check storage and review again. This does not mean old skills were lost."):t("未保存：名称重复、技能内容冲突、库已满或版本变化。旧技能保留。","Not saved: duplicate name, conflicting skill, full library or version change. Existing skills kept.");refresh();}).show();}
    private void run(){WorkflowStore store=new WorkflowStore(this);String raw=store.approved();if(raw==null||busy)return;
        new AlertDialog.Builder(this).setTitle(t("执行已保存的技能？","Run the saved skill?"))
            .setMessage(TeachingGuide.render(raw,en,WorkflowResourceStore.read(this))+t("\n请从指南指定的起始页面开始，且没有未保存修改。","\nStart at the page specified in the guide, without unsaved changes."))
            .setNegativeButton(t("取消","Cancel"),null).setPositiveButton(t("执行","Run"),(d,w)->{try{if(!raw.equals(store.approved()))throw new IllegalStateException();ProbeService s=ProbeService.current();if(s==null)throw new IllegalStateException();s.prepareWorkflow();message="";}catch(Exception e){message=t("未能执行。请检查服务、App 版本和已保存技能。","Could not run. Check service, App version and saved skill.");}refresh();}).show();}
    private void openTarget(){startActivity(new Intent().setClassName(WorkflowUi.PKG,WorkflowUi.PKG+".WorkflowActivity"));}
    private TeachingStatus.Data data(){
        TeachingStatus.Data d=new TeachingStatus.Data();ProbeService s=ProbeService.current();d.connected=s!=null;d.busy=busy;
        if(s!=null){WorkflowRecorder r=s.workflowRecorder();d.active=r.active();d.ready=r.ready();d.pending=r.hasPending();d.inspecting=r.inspectingLayout();d.running=s.workflowRunning();d.preparing=s.workflowPreparing();}
        try{JSONObject tr=new JSONObject(trace());d.selected=selected(tr);d.end=tr.optString("end");d.error=tr.optString("error");d.steps=tr.getJSONArray("steps").length();
            JSONObject last=tr.optJSONObject("final");d.flexible=tr.optInt("version")==2;d.savedOverview=last!=null&&(d.flexible?java.util.List.of("overview","single").contains(last.optString("page")):"overview".equals(last.optString("page")))&&!last.optBoolean("dirty",true);
            d.routeValid=d.flexible?flexibleComplete(tr):TeachingRoute.complete(TeachingRecordView.ids(tr));
            String draft=draft();d.draft=draft!=null;d.saved=draft!=null&&draft.equals(new WorkflowStore(this).approved());
        }catch(Exception ignored){}return d;
    }
    private boolean flexibleComplete(JSONObject trace){try{FlexibleWorkflowCodec.compile(trace.toString());return true;}catch(Exception e){return false;}}
    private void refresh(){if(status==null)return;ProbeService s=ProbeService.current();TeachingStatus.Data d=data();String kind=TeachingStatus.kind(d);
        Ui.stage(stageViews,kind,en);
        setText(stateTitle,TeachingStatus.title(kind,en));setText(stateHint,TeachingStatus.hint(kind,d.error.isEmpty()?d.end:d.error,d.steps,en));
        boolean warning=kind.equals("ERROR")||kind.equals("INCOMPLETE")||kind.equals("DISCONNECTED");header.setBackground(round(warning?UiStyle.WARNING_SURFACE:kind.equals("CANCELLED")?UiStyle.DISABLED:UiStyle.SOFT));stateTitle.setTextColor(warning?UiStyle.WARNING:UiStyle.INK);
        String provenance="";try{JSONObject tr=new JSONObject(trace());if(d.selected)provenance=TeachingText.recordOrigin(tr.optString("source"),en);}catch(Exception ignored){}
        setText(status,provenance+(message.isEmpty()?"":"\n"+message));status.setVisibility(status.getText().length()==0?View.GONE:View.VISIBLE);
        boolean free=!busy&&!d.active&&!d.running&&!d.preparing;
        recordSummary.setVisibility(d.selected&&!d.active&&!d.running&&!d.draft?View.VISIBLE:View.GONE);
        if(d.selected&&!d.active)try{setText(recordActions,TeachingRecordView.actions(new JSONObject(trace()),en));}catch(Exception ignored){}
        preparation.setVisibility(!d.selected&&!d.active&&!busy&&!d.running?View.VISIBLE:View.GONE);
        record.setEnabled(TeachingStatus.canStart(d));name.setEnabled(free);goal.setEnabled(free);
        stop.setVisibility(d.active?View.VISIBLE:View.GONE);stop.setEnabled(d.ready&&!d.pending&&!d.inspecting);
        cancel.setVisibility(d.active?View.VISIBLE:View.GONE);resume.setVisibility(d.active?View.VISIBLE:View.GONE);
        progress.setVisibility(d.active?View.VISIBLE:View.GONE);if(d.active&&s!=null)setText(progress,TeachingStatus.clock(s.workflowRecorder().elapsedMs())+t(" · 已记录 "," · Recorded ")+d.steps+t(" 步\n"," steps\n")+(d.ready&&!d.pending?s.workflowRecorder().nextAction(en):TeachingStatus.hint(kind,d.error,d.steps,en))+t("\n最近确认：","\nLast confirmed: ")+s.workflowRecorder().lastAction(en));
        boolean canGenerate=TeachingStatus.canGenerate(kind);
        review.setVisibility(canGenerate||d.draft||busy?View.VISIBLE:View.GONE);generate.setVisibility(canGenerate||busy?View.VISIBLE:View.GONE);generate.setEnabled(canGenerate&&free);
        String raw=draft();guide.setVisibility(raw!=null?View.VISIBLE:View.GONE);guideScroll.setVisibility(raw!=null?View.VISIBLE:View.GONE);guideHint.setVisibility(raw!=null?View.VISIBLE:View.GONE);save.setVisibility(raw!=null&&!d.saved?View.VISIBLE:View.GONE);save.setEnabled(raw!=null&&free);
        if(raw!=null)setText(guide,TeachingGuide.render(raw,en,WorkflowResourceStore.read(this)));
        restart.setVisibility(d.selected&&free?View.VISIBLE:View.GONE);restart.setText(t("开始一份新录制","Start a new recording"));
        WorkflowStore store=new WorkflowStore(this);run.setEnabled(store.approved()!=null&&d.connected&&free);runStop.setVisibility(d.running?View.VISIBLE:View.GONE);
        if(d.running||d.saved)library.setVisibility(View.VISIBLE);
        setText(savedInfo,store.approved()==null?t("暂无已保存技能。","No saved skill."):store.name()+"\n"+result(store));
    }
    private String result(WorkflowStore store){try{JSONObject r=new JSONObject(store.result());JSONObject skill=WorkflowCodec.decode(store.approved());if(!r.getString("traceSha256").equals(skill.getString("traceSha256")))return t("已保存；这份技能尚无执行结果。","Saved; no result for this skill yet.");String state=r.getString("status");return UiCopy.runState(state,en)+(state.equals("SUCCEEDED")||state.equals("RUNNING")?"":"\n"+UiCopy.failure(r.optString("reason"),en));}catch(Exception e){return t("已保存；尚未执行验证。","Saved; not execution-verified yet.");}}
    @Override protected void onResume(){super.onResume();ProbeService s=ProbeService.current();if(s!=null){if(s.workflowPreparing()){s.stopAll();message=t("准备已取消，尚未开始正式任务。","Preparation cancelled; no formal task started.");}s.teachingControls().remove();}handler.post(poll);}
    @Override protected void onPause(){persistInputs();handler.removeCallbacks(poll);super.onPause();}
    @Override protected void onDestroy(){guard.cancel();handler.removeCallbacks(poll);super.onDestroy();}
    private void dialog(String title,String message){new AlertDialog.Builder(this).setTitle(title).setMessage(message).setPositiveButton(t("知道了","OK"),null).show();}
    private int id(String key){return getResources().getIdentifier(key,"id",getPackageName());}
    private int dp(int value){return (int)(value*getResources().getDisplayMetrics().density);}
    private android.graphics.drawable.GradientDrawable round(int color){return Ui.surface(this,color);}
    private LinearLayout group(){LinearLayout group=new LinearLayout(this);group.setOrientation(1);group.setPadding(0,dp(8),0,dp(12));column.addView(group,new LinearLayout.LayoutParams(-1,-2));column=group;return group;}
    private void primary(Button b){Ui.button(b,true);}
    private void setText(TextView v,String text){if(!text.contentEquals(v.getText()))v.setText(text);}
    private TextView text(String value,int size){return Ui.label(column,value,size);}
    private String metadataError(IllegalArgumentException e){return t("输入未接受：名称最多60、目标最多240个UTF-16单元；请检查空白或非法字符。原文不会截短。代码：","Input rejected: name ≤60 and goal ≤240 UTF-16 units. Check blank or invalid characters; input is not shortened. Code: ")+e.getMessage();}
    private EditText input(String key,String value,int max){EditText v=new EditText(this);v.setId(id(key));v.setText(value);if(key.equals("teachPairing"))v.setFilters(new InputFilter[]{new InputFilter.LengthFilter(max)});Ui.field(v);column.addView(v);return v;}
    private Button button(String key,String label,Runnable action){return Ui.action(column,key,label,action,false);}
}
