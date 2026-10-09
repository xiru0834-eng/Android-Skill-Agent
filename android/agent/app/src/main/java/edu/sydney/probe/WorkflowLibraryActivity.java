package edu.sydney.probe;
import android.app.*;
import android.content.*;
import android.os.*;
import android.text.TextWatcher;
import android.text.Editable;
import android.widget.*;
import org.json.*;

/** Reviewed catalog only. Language selects; confirmation and execution stay local. */
public final class WorkflowLibraryActivity extends Activity {
    private LinearLayout column,list;
    private TextView status,catalogCount,lastExecution;
    private EditText input,filter;
    private Button choose,cancel,viewResult;
    private String diagnostics="";
    private boolean en,busy;
    private long generation;
    private final Handler handler=new Handler(Looper.getMainLooper());
    private WorkflowStore store;
    private WorkflowSelectionClient.Request activeSelection;
    private Runnable selectionTimeout;
    private String t(String zh,String english){return en?english:zh;}
    @Override public void onCreate(Bundle saved){super.onCreate(saved);store=new WorkflowStore(this);en=getSharedPreferences("language_connection",0).getBoolean("english",false);draw();}
    private void draw(){
        String text=input==null?getPreferences(0).getString("text",""):input.getText().toString();
        String query=filter==null?"":filter.getText().toString();
        column=Ui.page(this);
        Ui.toolbar(column,t("我的技能","My skills"),"libraryLanguage",en?"中文":"English",()->{invalidate();en=!en;getSharedPreferences("language_connection",0).edit().putBoolean("english",en).apply();draw();},"libraryBack",t("返回首页","Back to home"),this::finish);
        LinearLayout page=column;
        column=Ui.panel(page);
        label(t("输入一句话","Enter a command"),18);
        input=new EditText(this);input.setId(id("libraryInput"));input.setHint(t("例如：执行阅读60","Example: Run Reading60"));input.setContentDescription(t("中文或英文指令","Chinese or English instruction"));input.setText(text);input.setMinLines(2);input.setMaxLines(4);input.setVerticalScrollBarEnabled(true);Ui.field(input);column.addView(input);
        input.addTextChangedListener(new TextWatcher(){
            public void beforeTextChanged(CharSequence s,int start,int count,int after){}
            public void onTextChanged(CharSequence s,int start,int before,int count){}
            public void afterTextChanged(Editable value){boolean pending=busy;invalidate();refreshInput();if(pending){setStatus(t("指令已修改，请重新选择。","Command changed. Please select again."));refresh();}}
        });
        choose=button("libraryChoose",t("理解指令，预览技能","Find a matching skill"),this::select);Ui.button(choose,true);
        label(t("指令和技能名称、目标会发给模型。需配对电脑，确认后执行。","The model receives your command and skill names/goals via the paired computer. You confirm before execution."),14);
        status=label("",16);status.setId(id("libraryStatus"));Ui.notice(status);status.setVisibility(android.view.View.GONE);status.setAccessibilityLiveRegion(android.view.View.ACCESSIBILITY_LIVE_REGION_POLITE);
        cancel=button("libraryCancel",t("取消选择 / 停止执行","Cancel selection / Stop execution"),()->{invalidate();ProbeService s=ProbeService.current();if(s!=null)s.stopAll();setStatus(t("已取消；迟到响应不会执行。","Cancelled; late responses cannot execute."));refresh();});
        cancel.setVisibility(android.view.View.GONE);
        lastExecution=label("",14);lastExecution.setVisibility(android.view.View.GONE);
        viewResult=button("libraryViewResult",t("查看最近执行结果","View latest execution result"),()->startActivity(ExecutionResultActivity.intent(this,ExecutionResultData.latestRunId(this))));
        Ui.quiet(viewResult);viewResult.setVisibility(android.view.View.GONE);
        column=page;Ui.gap(column,24);label(t("已保存的技能","Saved routines"),20);catalogCount=label("",14);
        button("libraryParameters",t("参数化调用 · 换数值，不重教","Parameter calls · change values without reteaching"),()->{if(idle())startActivity(new Intent(this,ParameterSkillActivity.class));});
        filter=new EditText(this);filter.setId(id("libraryFilter"));filter.setSingleLine(true);filter.setHint(t("查找已保存的技能","Search saved skills"));filter.setContentDescription(t("本地查找技能，不调用模型","Local skill search, no model call"));filter.setText(query);Ui.field(filter);column.addView(filter);
        filter.addTextChangedListener(new TextWatcher(){public void beforeTextChanged(CharSequence s,int start,int count,int after){}public void onTextChanged(CharSequence s,int start,int before,int count){}public void afterTextChanged(Editable value){refresh();}});
        LinearLayout body=column;list=Ui.column(this);body.addView(list);
        Ui.divider(column);LinearLayout tools=Ui.column(this);
        Button more=button("libraryTools",t("管理与设置  ＋","Manage & settings  ＋"),()->{});
        Ui.quiet(more);
        more.setOnClickListener(v->{boolean show=tools.getVisibility()!=android.view.View.VISIBLE;tools.setVisibility(show?android.view.View.VISIBLE:android.view.View.GONE);more.setText(show?t("收起管理与设置  −","Hide settings  −"):t("管理与设置  ＋","Manage & settings  ＋"));});
        body.addView(tools);tools.setVisibility(android.view.View.GONE);column=tools;
        button("libraryTeach",t("＋ 教一个新流程","＋ Teach a workflow"),()->startActivity(new Intent(this,TeachingActivity.class)));
        button("libraryImport",t("导入技能包","Import skill package"),()->files(false,null));
        button("libraryReview",t("审核导入的技能（不会直接运行）","Review imported skill (does not run)"),this::reviewImport);
        button("libraryRefresh",t("刷新技能与结果","Refresh skills & results"),this::refresh);
        button("libraryConnection",t("电脑配对设置","Computer pairing"),()->startActivity(new Intent(this,TeachingActivity.class).putExtra("pairingSetup",true)));
        button("libraryDiagnostics",t("查看技术详情","Technical details"),()->new AlertDialog.Builder(this).setTitle(t("技术详情","Technical details")).setMessage(diagnostics.isEmpty()?store.result():diagnostics).setPositiveButton(t("关闭","Close"),null).show());
        column=body;refresh();
    }
    private JSONArray catalog() throws Exception {
        JSONArray data=new JSONArray();for(var e:store.entries()){JSONObject s=WorkflowCodec.decode(e.raw);
            if(store.sameVersion(e.raw)){JSONObject entry=new JSONObject().put("id",e.id).put("name",e.name).put("goal",s.getString("goal")).put("finalGoals",s.getJSONArray("finalGoals"));
                if(s.getInt("version")==3)entry.put("processMode","ORDERED");data.put(entry);}}
        return data;
    }
    private boolean idle(){ProbeService s=ProbeService.current();return !busy&&(s==null||(!s.workflowRunning()&&!s.workflowRecorder().active()&&!s.workflowPreparing()));}
    private void select(){
        if(!idle())return;
        try{
            String text=SelectionText.checked(input.getText().toString());
            JSONArray snapshot=catalog();if(snapshot.length()==0)throw new IllegalArgumentException("NO_COMPATIBLE_SKILL");
            String token=getSharedPreferences("language_connection",0).getString("pairing","");
            WorkflowSelectionClient.Request request=new WorkflowSelectionClient.Request(text,snapshot,token);
            activeSelection=request;
            long ticket=++generation;busy=true;choose.setEnabled(false);cancel.setVisibility(android.view.View.VISIBLE);setStatus(t("正在理解指令，尚未执行…","Understanding the command; nothing has run…"));
            selectionTimeout=()->{if(ticket==generation&&busy){invalidate();setStatus(t("选择超时，尚未执行。请检查连接后重试。","Selection timed out; nothing ran. Check the connection before trying again."));refresh();}};
            handler.postDelayed(selectionTimeout,9000);
            request.start((result,failure)->handler.post(()->{
                if(ticket!=generation||isDestroyed())return;
                // A queued main-thread callback can be delivered after its network
                // thread finished. Check monotonic authority again before preview.
                try{request.assertCurrent();}catch(Exception expired){invalidate();error(expired);return;}
                finishSelection();
                if(failure!=null){error(failure);return;}
                try{
                    WorkflowSelectionClient.validateSnapshot(text,SelectionText.checked(input.getText().toString()),snapshot.toString(),catalog().toString());
                    setStatus(UiCopy.selection(result.getString("status"),en)+"\n"+result.getString("message"));refresh();
                    if("invoke".equals(result.getString("status")))confirmRun(store.find(result.getString("skill_id")));
                }catch(Exception e){error(e);}
            }));
        }catch(Exception e){invalidate();error(e);}
    }
    private void confirmRun(NamedWorkflowPolicy.Entry entry){
        if(entry==null||!idle())return;long ticket=generation;
        new AlertDialog.Builder(this).setTitle(t("确认执行：","Confirm: ")+entry.name)
            .setMessage(TeachingGuide.render(entry.raw,en,WorkflowResourceStore.read(this))+t("\n从指南指定的起始页面开始；未保存修改时不执行。","\nStart at the page specified in the guide. Unsaved edits prevent execution."))
            .setNegativeButton(t("取消","Cancel"),null).setPositiveButton(t("确认执行","Run"),(d,w)->{
                try{if(ticket!=generation||!idle())throw new IllegalArgumentException("STALE_CONFIRMATION");
                    ProbeService s=ProbeService.current();if(s==null)throw new IllegalArgumentException("SERVICE_OFF");
                    if(!store.activate(entry))throw new IllegalArgumentException("SKILL_CHANGED_OR_INCOMPATIBLE");
                    s.prepareWorkflow();
                }catch(Exception e){error(e);}
            }).show();
    }
    private void reviewImport(){
        if(!idle())return;String raw=store.pendingNamed();if(raw==null){setStatus(t("没有待审技能包。","No imported draft."));return;}
        try{var e=NamedWorkflowCodec.decode(raw);new AlertDialog.Builder(this).setTitle(t("审核：","Review: ")+e.name)
            .setMessage(TeachingGuide.render(e.raw,en,WorkflowResourceStore.read(this))+t("\n来源是文件声明。不会携带原设备审批；运行时重新定位检查。","\nSource is a file claim. Approval is local; bindings are checked during execution."))
            .setNegativeButton(t("取消","Cancel"),null).setPositiveButton(t("确认保存","Save"),(d,w)->{
                if(!idle())return;try{if(!store.reviewImported(raw))throw new IllegalArgumentException("NAME_CONFLICT_OR_INCOMPATIBLE");setStatus(t("已保存，尚未执行。","Saved; not executed."));refresh();}catch(Exception ex){error(ex);}
            }).show();}catch(Exception e){error(e);}
    }
    private void files(boolean export,NamedWorkflowPolicy.Entry entry){if(!idle())return;
        Intent intent=new Intent(this,SkillFileActivity.class).putExtra("namedWorkflow",true).putExtra("mode",export?"EXPORT":"IMPORT");
        if(entry!=null)intent.putExtra("skillId",entry.id);startActivity(intent);
    }
    private void refresh(){if(list==null)return;list.removeAllViews();LinearLayout body=column;column=list;
        try{int index=0,shown=0;for(var e:store.entries()){
            JSONObject skill=WorkflowCodec.decode(e.raw);final int n=index++;
            if(!UiPresentation.matches(e.name,skill.optString("goal"),filter.getText().toString()))continue;
            shown++;column=Ui.panel(list);
            label(e.name,20);
            label(UiPresentation.skillSteps(skill.getJSONArray("steps").length(),en),14);
            label(TeachingGuide.goals(skill.getJSONArray("finalGoals"),en),14);
            Button preview=button("libraryRun"+n,t("查看步骤并执行","Preview & run"),()->{if(idle())confirmRun(e);});
            Button export=button("libraryExport"+n,t("导出","Export"),()->files(true,e));Ui.quiet(export);
            Ui.pair(column,preview,export,2,1);
        }column=list;if(index==0)label(t("还没有技能。先录制一个流程，或在下方导入技能包。","No skills yet. Teach a routine or import a package below."),16);
            else if(shown==0)label(t("没有匹配的技能。换个词，或清空查找内容。","No matching routine. Try another word or clear the search."),16);
            catalogCount.setText(en?shown+" of "+index+" skills · preview before running":"显示 "+shown+" / "+index+" 条 · 执行前预览");
            lastExecution.setVisibility(android.view.View.GONE);
            viewResult.setVisibility(ExecutionResultData.latestRunId(this).isEmpty()?android.view.View.GONE:android.view.View.VISIBLE);
            String result=store.result();try{JSONObject r=new JSONObject(result);var e=store.find(r.optString("traceSha256"));
                if(e!=null){lastExecution.setText(t("最近执行：","Last run: ")+e.name+" · "+UiCopy.runOutcome(r.optString("status"),en));lastExecution.setVisibility(android.view.View.VISIBLE);}
            }catch(Exception ignored){}
        }catch(Exception e){error(e);}finally{column=body;refreshInput();ProbeService s=ProbeService.current();if(cancel!=null)cancel.setVisibility(busy||(s!=null&&s.workflowRunning())?android.view.View.VISIBLE:android.view.View.GONE);}
    }
    private void refreshInput(){
        if(input==null||choose==null)return;
        String raw=input.getText().toString();String reason=null;
        try{SelectionText.checked(raw);}catch(IllegalArgumentException invalid){reason=invalid.getMessage();}
        input.setError(reason==null||raw.isEmpty()?null:UiCopy.failure(reason,en));
        choose.setEnabled(reason==null&&idle());
    }
    private void setStatus(String value){status.setText(value);status.setVisibility(value.isEmpty()?android.view.View.GONE:android.view.View.VISIBLE);}
    private void error(Exception e){diagnostics=e.getClass().getSimpleName()+(e instanceof IllegalArgumentException?" / "+e.getMessage():"");setStatus(UiCopy.failure(e.getMessage(),en)+t("\n请检查连接、名称或版本；技术原因见“管理与设置”。","\nCheck connection, name or version. Technical details are under Manage & settings."));if(cancel!=null)cancel.setVisibility(busy?android.view.View.VISIBLE:android.view.View.GONE);}
    private void finishSelection(){if(selectionTimeout!=null)handler.removeCallbacks(selectionTimeout);selectionTimeout=null;activeSelection=null;busy=false;refreshInput();}
    private void invalidate(){generation++;WorkflowSelectionClient.Request request=activeSelection;finishSelection();if(request!=null)request.cancel();}
    @Override protected void onResume(){super.onResume();ProbeService s=ProbeService.current();if(s!=null&&s.workflowPreparing()){s.stopAll();setStatus(t("准备已取消；尚未执行。","Preparation cancelled; nothing executed."));}refresh();if(s!=null&&!s.workflowRunning()&&!s.workflowRecorder().active())s.teachingControls().remove();}
    @Override protected void onPause(){invalidate();getPreferences(0).edit().putString("text",input.getText().toString()).apply();super.onPause();}
    @Override protected void onDestroy(){invalidate();super.onDestroy();}
    private int id(String key){return getResources().getIdentifier(key,"id",getPackageName());}
    private TextView label(String value,int size){return Ui.label(column,value,size);}
    private Button button(String key,String text,Runnable action){return Ui.action(column,key,text,action,false);}
}
