package edu.sydney.probe;
import android.app.*;
import android.os.*;
import android.widget.*;
import android.text.*;
import org.json.*;
import java.util.*;

/** Parameter entry keeps both model output and execution permission visible. */
public final class ParameterSkillActivity extends Activity {
    private boolean en,busy;
    private long generation;
    private final Handler handler=new Handler(Looper.getMainLooper());
    private WorkflowSelectionClient.Request pending;
    private WorkflowStore store;
    private final List<NamedWorkflowPolicy.Entry> sources=new ArrayList<>();
    private LinearLayout column;
    private Spinner source,capability;
    private EditText command,value;
    private TextView status,queue;
    private Button understand,add,run,save;
    private JSONArray calls=new JSONArray();
    private String t(String zh,String english){return en?english:zh;}
    @Override public void onCreate(Bundle state){super.onCreate(state);store=new WorkflowStore(this);en=getSharedPreferences("language_connection",0).getBoolean("english",false);draw();}
    private void draw(){
        String selectedId=null;
        if(source!=null){int position=source.getSelectedItemPosition();if(position>=0&&position<sources.size())selectedId=sources.get(position).id;}
        sources.clear();try{if(!store.storageUnconfirmed())for(var entry:store.entries())try{if(store.sameVersion(entry.raw)){ParameterSkillCodec.catalog(ParameterSkillCodec.binding(entry.raw));sources.add(entry);}}catch(Exception ignored){}}catch(Exception ignored){}
        column=Ui.page(this);Ui.toolbar(column,t("参数化技能","Parameter skills"),"parameterLanguage",en?"中文":"English",()->{invalidate();en=!en;getSharedPreferences("language_connection",0).edit().putBoolean("english",en).apply();calls=new JSONArray();draw();},"parameterBack",t("返回","Back"),this::finish);
        label(t("1 · 选择本机技能","1 · Select a local skill"),20);
        label(t("使用已审核示范和本机绑定。换参数直接调用，不必重新录制或保存 JSON。","Uses reviewed evidence and local bindings. Change parameters directly; no new recording or JSON file is needed."),14);
        source=new Spinner(this);source.setId(id("parameterSource"));List<String> names=new ArrayList<>();for(var e:sources)names.add(e.name);
        source.setAdapter(new ArrayAdapter<>(this,android.R.layout.simple_spinner_dropdown_item,names));column.addView(source);
        for(int i=0;i<sources.size();i++)if(sources.get(i).id.equals(selectedId)){source.setSelection(i);break;}
        source.setOnItemSelectedListener(new AdapterView.OnItemSelectedListener(){public void onNothingSelected(AdapterView<?> parent){}public void onItemSelected(AdapterView<?> p,android.view.View v,int pos,long key){invalidate();calls=new JSONArray();refreshCapabilities();}});
        label(t("2 · 输入指令","2 · Enter a command"),20);
        command=new EditText(this);command.setId(id("parameterInput"));command.setHint(t("把卧室灯调到80%，风扇调到2档","Set bedroom light to 80 percent and fan to speed 2"));command.setMinLines(2);Ui.field(command);column.addView(command);
        watch(command);
        understand=button("parameterUnderstand",t("GPT 理解并预览","Understand & preview with GPT"),this::understand);
        label(t("只发送文字与语义能力，不发送屏幕。模糊参数先澄清，确认前不操作。","Only text and semantic capabilities are sent, not screenshots. Ambiguous values need clarification. No input before confirmation."),14);
        status=label("",16);status.setId(id("parameterStatus"));Ui.notice(status);status.setAccessibilityLiveRegion(android.view.View.ACCESSIBILITY_LIVE_REGION_POLITE);
        label(t("本地结构化调用（不调用模型）","Local structured calls (no model request)"),16);
        capability=new Spinner(this);capability.setId(id("parameterCapability"));column.addView(capability);
        value=new EditText(this);value.setId(id("parameterValue"));value.setSingleLine(true);value.setHint(t("开关填 on/off；亮度填20/40/60/80/100；风速填1/2/3","on/off; brightness 20/40/60/80/100; speed 1/2/3"));Ui.field(value);column.addView(value);watch(value);
        add=button("parameterAdd",t("＋ 添加调用","＋ Add call"),this::addCall);
        queue=label("",14);queue.setId(id("parameterQueue"));
        run=button("parameterRun",t("预览调用并执行","Preview calls & run"),()->preview(calls));
        button("parameterClear",t("清空调用","Clear calls"),()->{invalidate();calls=new JSONArray();update();});
        button("parameterStop",t("取消 / 停止","Cancel / Stop"),()->{invalidate();ProbeService s=ProbeService.current();if(s!=null)s.stopAll();show(t("已取消；迟到响应不会执行。","Cancelled; late responses cannot execute."));});
        button("parameterResult",t("查看最近结果","View latest result"),()->startActivity(ExecutionResultActivity.intent(this,ExecutionResultData.latestRunId(this))));
        save=button("parameterSave",t("保存操作包副本（可选）","Save package copy (optional)"),this::saveBinding);
        label(t("副本用于后续导出，不影响本机调用。新设备仍须重新检查绑定并审核。","The copy is for later export, not required for local calls. A new device still needs binding checks and review."),14);
        refreshCapabilities();
    }
    private NamedWorkflowPolicy.Entry selected(){if(sources.isEmpty())throw new IllegalArgumentException("NO_PARAMETER_SOURCE");return sources.get(source.getSelectedItemPosition());}
    private void refreshCapabilities(){if(capability==null)return;List<String> choices=new ArrayList<>();
        try{JSONArray catalog=ParameterSkillCodec.catalog(ParameterSkillCodec.binding(selected().raw));
            for(int i=0;i<catalog.length();i++){var row=catalog.getJSONObject(i);for(int c=0;c<row.getJSONArray("skills").length();c++)choices.add(row.getJSONArray("skills").getString(c)+" | "+row.getString("device"));}}
        catch(Exception error){show(t("没有可用的已审核示范。","No compatible reviewed demonstration."));}
        capability.setAdapter(new ArrayAdapter<>(this,android.R.layout.simple_spinner_dropdown_item,choices));update();
    }
    private boolean idle(){ProbeService s=ProbeService.current();return !busy&&(s==null||(!s.workflowRunning()&&!s.workflowPreparing()&&!s.workflowRecorder().active()));}
    private void saveBinding(){if(!idle())return;try{var entry=selected();long ticket=generation;
        ParameterBindingStore.localSnapshot(this,entry);
        String description=ParameterSkillCodec.catalog(ParameterSkillCodec.binding(entry.raw)).toString(2);
        new AlertDialog.Builder(this).setTitle(t("确认参数能力与绑定","Confirm capabilities & binding")).setMessage(entry.name+"\n"+description+t("\n仅已示范类别 + 实验 App 适配器。不是自动学习任意界面。原示范不会修改。","\nDemonstrated categories + the lab adapter only. Not arbitrary UI learning. Original demonstration is unchanged."))
            .setNegativeButton(t("取消","Cancel"),null).setPositiveButton(t("确认保存","Save"),(d,w)->{try{current(entry,ticket);ParameterBindingStore.save(this,entry);show(t("参数技能已保存，尚未执行。","Parameter skill saved; nothing executed."));}catch(Exception e){error(e);}}).show();
        }catch(Exception e){error(e);}}
    private void addCall(){if(!idle())return;try{String[] choice=String.valueOf(capability.getSelectedItem()).split(" \\| ");if(choice.length!=2)throw new IllegalArgumentException("CAPABILITY");
        String raw=value.getText().toString().trim();Object parameter=choice[0].equals("SetPower")?raw:Integer.valueOf(raw);
        JSONObject call=new JSONObject().put("skill",choice[0]).put("args",new JSONObject().put("device",choice[1]).put(ParameterSkillCodec.argument(choice[0]),parameter));
        JSONArray next=new JSONArray(calls.toString()).put(call);ParameterSkills.compile(ParameterSkillCodec.binding(selected().raw),ParameterSkillCodec.calls(next));calls=next;update();
        }catch(Exception e){error(e);}}
    private void understand(){if(!idle())return;calls=new JSONArray();update();try{
        var entry=selected();ParameterBindingStore.localSnapshot(this,entry);var input=new ParameterText.Snapshot(command.getText().toString());String text=input.text;JSONArray catalog=ParameterSkillCodec.semanticCatalog(ParameterSkillCodec.binding(entry.raw));
        var request=new WorkflowSelectionClient.Request(text,catalog,getSharedPreferences("language_connection",0).getString("pairing",""),WorkflowSelectionClient.Kind.SEMANTIC);pending=request;long ticket=++generation;busy=true;update();show(t("正在理解，尚未执行…","Understanding; nothing has executed…"));
        handler.postDelayed(()->{if(ticket==generation&&busy){invalidate();error(new IllegalArgumentException("SELECTION_DEADLINE"),"parsing");}},9000);
        request.start((result,failure)->handler.post(()->{if(ticket!=generation||isDestroyed())return;try{request.assertCurrent();if(failure!=null)throw failure;currentSource(entry);
            if(!input.current(command.getText().toString()))throw new IllegalArgumentException("SELECTION_CHANGED");busy=false;pending=null;handler.removeCallbacksAndMessages(null);show(result.getString("message"));
            calls=result.getJSONArray("calls");update();if(result.getString("status").equals("invoke"))preview(calls);
            else ParameterEntryEvidence.record(this,result.getString("status").equals("reject")?"MODEL_REJECTED":"CLARIFICATION_REQUIRED");
        }catch(Exception e){invalidate();error(e,"parsing");}}));
        }catch(Exception e){invalidate();error(e,"parsing");}}
    private void preview(JSONArray requested){if(!idle())return;try{
        var entry=selected();ParameterBindingStore.localSnapshot(this,entry);JSONArray snapshot=new JSONArray(requested.toString());JSONObject plan=ParameterSkillCodec.compile(entry.raw,snapshot);long ticket=generation;
        String message=entry.name+"\n"+snapshot.toString(2)+"\n"+TeachingGuide.goals(plan.getJSONArray("finalGoals"),en)+t("\n未提及字段保持不变。使用源示范布局；准备后需再点开始执行。","\nUnmentioned fields stay unchanged. Uses the source layout; tap Start execution after preparation.");
        new AlertDialog.Builder(this).setTitle(t("确认技能 + 参数","Confirm skill + parameters")).setMessage(message).setNegativeButton(t("取消","Cancel"),null).setPositiveButton(t("确认执行","Run"),(d,w)->{
            try{current(entry,ticket);var invocation=new ParameterExecution(this,entry,snapshot);ProbeService s=ProbeService.current();if(s==null)throw new IllegalArgumentException("SERVICE_OFF");s.prepareParameters(invocation);}catch(Exception e){error(e);}}).show();
        }catch(Exception e){error(e);}}
    private void currentSource(NamedWorkflowPolicy.Entry entry)throws Exception {ParameterBindingStore.localSnapshot(this,entry);if(!selected().id.equals(entry.id))throw new IllegalArgumentException("PARAMETER_BINDING_CHANGED");}
    private void current(NamedWorkflowPolicy.Entry entry,long ticket)throws Exception {if(ticket!=generation||!idle())throw new IllegalArgumentException("STALE_CONFIRMATION");currentSource(entry);}
    private void invalidate(){generation++;if(pending!=null)pending.cancel();pending=null;busy=false;handler.removeCallbacksAndMessages(null);update();}
    private void update(){if(understand==null)return;boolean ready=idle()&&!sources.isEmpty();understand.setEnabled(ready);add.setEnabled(ready);save.setEnabled(ready);run.setEnabled(ready&&calls.length()>0);queue.setText(calls.length()==0?t("尚无调用","No calls yet"):calls.toString());}
    private void show(String text){if(status!=null)status.setText(text);}
    private void error(Exception error){
        error(error,"validation");
    }
    private void error(Exception error,String fallbackStage){
        try{String reason=ParameterOutcome.entryReason(error.getMessage(),error instanceof IllegalArgumentException,fallbackStage);
            JSONObject entry=ParameterEntryEvidence.record(this,reason,fallbackStage);
            show(ParameterEntryHelp.text(entry.getString("reason"),en)+"\n"+t("技术信息：","Technical details: ")+entry.getString("status")+" / "+entry.getString("failureStage")+" / "+entry.getString("reason"));}
        catch(Exception evidenceFailure){show(t("未开始执行；入口证据保存失败，请检查存储。","Nothing started; entry evidence could not be saved. Check storage."));}
    }
    private void watch(EditText field){field.addTextChangedListener(new TextWatcher(){public void beforeTextChanged(CharSequence s,int a,int c,int f){}public void onTextChanged(CharSequence s,int a,int b,int c){}public void afterTextChanged(Editable text){if(field==command)calls=new JSONArray();invalidate();}});}
    @Override protected void onPause(){invalidate();super.onPause();}
    @Override protected void onResume(){super.onResume();ProbeService s=ProbeService.current();if(s!=null&&s.workflowPreparing())s.stopAll();update();}
    @Override protected void onDestroy(){invalidate();super.onDestroy();}
    private int id(String key){return getResources().getIdentifier(key,"id",getPackageName());}
    private TextView label(String text,int size){return Ui.label(column,text,size);}
    private Button button(String id,String text,Runnable action){return Ui.action(column,id,text,action,false);}
}
