package edu.sydney.probe;
import android.app.*;
import android.os.*;
import android.widget.*;
import org.json.*;
import java.util.*;

/** Normal candidate UI, separate from the formal Flow calling entrance. */
public final class UserCandidateActivity extends Activity {
    private boolean en,busy,executing;private long ticket;private String candidate="",attempt="";
    private JSONObject flow;private LinearLayout fields;private EditText name;private TextView status;
    private final Map<String,android.view.View> controls=new LinkedHashMap<>();
    private UserLearningClient client;private UserCandidateGate gate;
    private boolean resumed;
    private static volatile String activeAttempt="";
    private static volatile Runnable activeCancellation;
    private interface Result {void accept(JSONObject result)throws Exception;}
    private final Handler handler=new Handler(Looper.getMainLooper());
    private String t(String zh,String english){return en?english:zh;}
    private int id(String key){int value=getResources().getIdentifier(key,"id",getPackageName());return value==0?android.view.View.generateViewId():value;}
    @Override public void onCreate(Bundle saved){super.onCreate(saved);
        en=getSharedPreferences("language_connection",0).getBoolean("english",false);candidate=getIntent().getStringExtra("candidate_id");
        var page=Ui.page(this);Ui.toolbar(page,t("检查与发布流程","Validate & publish Flow"),"candidateReload",t("刷新","Refresh"),this::load,"candidateBack",t("返回","Back"),this::finish);
        Ui.label(page,t("先实测，再发布","Validate before publishing"),22);
        Ui.label(page,t("这里只使用新学习草稿。选择本次业务对象和参数，预览后才执行。只核验过的参数会列为实测，不代表全域已证明。","New learning draft only. Select business entity and parameters, then preview before execution. Tested points do not prove the whole domain."),14);
        fields=Ui.column(this);page.addView(fields);
        Ui.action(page,"candidateValidate",t("预览本次候选实测","Preview candidate validation"),this::prepare,true);
        Ui.action(page,"candidateResult",t("读取实测结果","Read validation result"),this::readResult,false);
        name=new EditText(this);name.setId(id("candidateName"));name.setHint(t("给流程起个名字","Name this Flow"));Ui.field(name);page.addView(name);
        Ui.action(page,"candidateSaveName",t("保存名称（仍不是发布）","Save name (not publication)"),()->{try{rpc("name",new JSONObject().put("name",name.getText().toString()),r->show(t("名称已保存。","Name saved.")));}catch(Exception e){error(e);}},false);
        Ui.action(page,"candidatePublish",t("确认发布并保存到本机","Confirm publish & save locally"),this::publish,false);
        Ui.action(page,"candidateLoadPublished",t("重新读取已发布包并本机审核","Reload published package for local review"),()->{if(idle())rpc("published",new JSONObject(),this::reviewPublished);},false);
        Ui.action(page,"candidateCancel",t("停止本次验证 / 撤销待确认","Stop validation / cancel pending preview"),this::cancel,false);
        status=Ui.label(page,"",14);status.setId(id("candidateStatus"));status.setAccessibilityLiveRegion(android.view.View.ACCESSIBILITY_LIVE_REGION_POLITE);Ui.notice(status);
        if(candidate==null||!candidate.matches("[a-f0-9]{32}")){show("REQUEST_ID");return;}load();
    }
    private boolean idle(){var s=ProbeService.current();return !busy&&!executing&&!UserLearningSession.active()&&(s==null||(!s.workflowRunning()&&!s.workflowPreparing()&&!s.isRecording()));}
    private void load(){if(!idle())return;if(gate!=null)gate.cancel();rpc("candidate_details",new JSONObject(),r->{
        var draft=r.getJSONObject("draft");flow=draft.getJSONObject("body").getJSONObject("generation").getJSONObject("candidate_flow");
        fields.removeAllViews();controls.clear();Ui.label(fields,flow.getString("id")+" @ "+flow.getString("version"),18);
        Ui.label(fields,flow.getString("purpose"),14);var specs=flow.getJSONArray("inputs");
        for(int i=0;i<specs.length();i++){
            var spec=specs.getJSONObject(i);String key=spec.getString("name"),type=spec.getString("type");Ui.label(fields,key+" · "+type,16);
            if(type.equals("integer")){
                var input=new EditText(this);input.setId(id("candidateValue"+i));input.setContentDescription(key);
                input.setInputType(android.text.InputType.TYPE_CLASS_NUMBER|android.text.InputType.TYPE_NUMBER_FLAG_SIGNED);
                input.setHint(spec.getInt("minimum")+"–"+spec.getInt("maximum")+" · "+spec.getString("unit"));Ui.field(input);fields.addView(input);controls.put(key,input);
            }else if(type.equals("entity")||type.equals("enum")){
                JSONArray options=type.equals("entity")?r.getJSONObject("entities").getJSONArray(key):spec.getJSONArray("choices");
                var values=new ArrayList<String>();values.add(t("请选择（不会默认猜测）","Select (no guessed default)"));for(int j=0;j<options.length();j++)values.add(options.getString(j));
                var select=new Spinner(this);select.setId(id("candidateValue"+i));select.setContentDescription(key);select.setAdapter(new ArrayAdapter<String>(this,android.R.layout.simple_spinner_dropdown_item,values));fields.addView(select);controls.put(key,select);
            }else throw new IllegalArgumentException("INPUT_TYPE_UNSUPPORTED");
        }
        name.setText(draft.optString("name",""));var state=r.getJSONObject("lifecycle");attempt=state.isNull("pending_attempt")?"":state.optString("pending_attempt","");
        show(state.toString(2)+"\n"+t("草稿未知项：","Draft unknowns: ")+flow.getJSONArray("unknowns"));
    });}
    private JSONObject inputs()throws Exception{
        if(flow==null)throw new IllegalStateException("DRAFT_NOT_LOADED");var out=new JSONObject();var specs=flow.getJSONArray("inputs");
        for(int i=0;i<specs.length();i++){
            var s=specs.getJSONObject(i);String key=s.getString("name"),type=s.getString("type");var v=controls.get(key);
            if(type.equals("integer")){
                String text=((EditText)v).getText().toString();if(!text.matches("-?(0|[1-9][0-9]{0,8})"))throw new IllegalArgumentException("INPUT_TYPE");
                int n=Integer.parseInt(text);if(n<s.getInt("minimum")||n>s.getInt("maximum")||(n-s.getInt("minimum"))%s.getInt("step")!=0)throw new IllegalArgumentException("INPUT_RANGE");out.put(key,n);
            }else{var spinner=(Spinner)v;if(spinner.getSelectedItemPosition()==0)throw new IllegalArgumentException("INPUT_REQUIRED");String value=spinner.getSelectedItem().toString();out.put(key,type.equals("entity")?new JSONObject().put("entity_id",value):value);}
        }return out;
    }
    private void prepare(){if(!idle())return;try{
        if(!attempt.isEmpty())throw new IllegalStateException("VALIDATION_PENDING");String snapshot=FlowKnowledgeStore.canonical(inputs());
        rpc("prepare_validation",new JSONObject().put("inputs",inputs()),r->{
            attempt=r.getString("attempt_id");var plan=r.getJSONObject("plan");
            if(!snapshot.equals(FlowKnowledgeStore.canonical(inputs())))throw new IllegalArgumentException("INPUT_CHANGED");
            if(!FlowDigest.sha256(FlowKnowledgeStore.canonical(plan)).equals(r.getString("plan_raw_hash")))throw new IllegalArgumentException("PLAN_CHANGED");
            gate=new UserCandidateGate(snapshot,SystemClock.elapsedRealtime());var confirmation=new PortableConfirmationGate();
            var dialog=new AlertDialog.Builder(this).setTitle(t("确认本次实测修改","Confirm this validation's changes"))
                .setMessage(inputs().toString(2)+"\n"+plan.getJSONArray("steps").toString(2)+"\n"+t("只改所列属性；保留其他状态。整体上限8秒，失败不自动重发。","Only listed changes; preserve other state. Whole limit 8 seconds; no automatic resend."))
                .setNegativeButton(t("取消","Cancel"),(d,w)->cancel()).setPositiveButton(t("确认实测","Validate"),(d,w)->confirmation.confirm()).create();
            dialog.setOnCancelListener(d->cancel());dialog.setOnDismissListener(d->{if(confirmation.dismiss())execute(r,plan,snapshot);});dialog.show();
        });
    }catch(Exception e){error(e);}}
    private void execute(JSONObject prepared,JSONObject plan,String snapshot){try{
        if(!resumed||isDestroyed()||isFinishing()||!idle()||gate==null||!gate.claim(FlowKnowledgeStore.canonical(inputs()),SystemClock.elapsedRealtime()))throw new IllegalStateException("STALE_CONFIRMATION");
        if(!snapshot.equals(FlowKnowledgeStore.canonical(inputs()))||!candidate.equals(prepared.getString("candidate_id"))||!attempt.equals(prepared.getString("attempt_id"))||!attempt.matches("[a-f0-9]{32}"))throw new IllegalArgumentException("VALIDATION_IDENTITY");
        if(!FlowDigest.sha256(FlowKnowledgeStore.canonical(plan)).equals(prepared.getString("plan_raw_hash"))||!prepared.getString("flow_hash").equals(plan.getString("flow_hash")))throw new IllegalArgumentException("PLAN_CHANGED");
        var service=ProbeService.current();if(service==null)throw new IllegalStateException("SERVICE_OFF");
        Set<String> writes=new TreeSet<>();var a=plan.getJSONArray("actual_write_set");for(int i=0;i<a.length();i++)writes.add(a.getString(i));
        final String run=attempt,draft=candidate,rawHash=prepared.getString("plan_raw_hash");final var app=getApplicationContext();
        executing=true;activeAttempt=run;show(t("正在执行本次已确认验证；不会自动重试。","Executing the confirmed validation; no automatic retry."));
        try{activeCancellation=service.runCandidateFlow(plan,writes,receipt->{
            Exception failure=null;
            try{
                receipt.put("request_id",run).put("candidate_id",draft).put("plan_raw_hash",rawHash).put("native_plan_raw",plan.toString()).put("transport_channel","NORMAL_USER_CANDIDATE_UI");
                byte[] bytes=receipt.toString().getBytes(java.nio.charset.StandardCharsets.UTF_8);if(bytes.length>1048576)throw new IllegalStateException("RECEIPT_SIZE_LIMIT");
                var file=new android.util.AtomicFile(new java.io.File(app.getFilesDir(),"c2-validation-"+run+".json"));java.io.FileOutputStream stream=null;
                try{stream=file.startWrite();stream.write(bytes);file.finishWrite(stream);}catch(Exception e){if(stream!=null)file.failWrite(stream);throw e;}
            }catch(Exception e){failure=e;}
            if(activeAttempt.equals(run)){activeAttempt="";activeCancellation=null;}final Exception problem=failure;
            handler.post(()->{executing=false;if(isDestroyed())return;if(problem!=null)error(problem);else show(receipt.optString("final_status","UNCONFIRMED")+"\n"+t("回执已保存。返回后点“读取实测结果”，服务器会完整核验；尚未发布。","Receipt saved. Return and read validation result for full checks; not published yet."));});
        });}catch(Exception e){executing=false;if(activeAttempt.equals(run)){activeAttempt="";activeCancellation=null;}throw e;}
    }catch(Exception e){error(e);}}
    private void readResult(){if(!idle()){show("BUSY");return;}if(attempt.isEmpty()){show(t("没有待读取的实测。","No pending validation."));return;}try{
        rpc("finish_validation",new JSONObject().put("attempt_id",attempt),r->{attempt="";show(r.toString(2)+"\n"+t("仅所列实际参数点有实测证据；还需命名并明确发布。","Only listed points are validated; name and explicitly publish next."));});
    }catch(Exception e){error(e);}}
    private void publish(){if(!idle())return;try{
        if(flow==null||!attempt.isEmpty())throw new IllegalStateException("VALIDATION_REQUIRED");
        String expectedName=name.getText().toString();long generation=ticket;
        new AlertDialog.Builder(this).setTitle(t("确认发布已验证流程","Publish the validated Flow"))
            .setMessage(t("服务器只接受已保存名称和真实设置实测。发布不会执行业务；下一步仍需本机审核保存。未验证参数域不会被标成已证明。","Server requires a saved name and real setting evidence. Publication does not execute; local review follows. Untested domains are not marked proven."))
            .setNegativeButton(t("取消","Cancel"),null).setPositiveButton(t("确认发布","Publish"),(d,w)->{try{
                if(generation!=ticket||!resumed||!idle()||!expectedName.equals(name.getText().toString()))throw new IllegalStateException("STALE_CONFIRMATION");
                rpc("publish",new JSONObject().put("confirmed",true),r->{show(t("服务器已发布；正在读取本机审核材料。","Published on server; reading local review material."));rpc("published",new JSONObject(),this::reviewPublished);});
            }catch(Exception e){error(e);}}).show();
    }catch(Exception e){error(e);}}
    private void reviewPublished(JSONObject result)throws Exception{
        var knowledge=new FlowKnowledgeStore(this);String raw=result.toString();var data=knowledge.decode(raw);long generation=ticket;
        new AlertDialog.Builder(this).setTitle(t("本机审核保存，不复制源授权","Local review; no inherited authority"))
            .setMessage(data.getJSONArray("catalog").toString(2)+"\n"+t("确认后保存在本机。不会自动执行；以后从“调用已发布流程”输入任务。","Save locally after confirmation. No automatic execution; use the published Flow task entrance later."))
            .setNegativeButton(t("稍后审核","Review later"),null).setPositiveButton(t("审核并保存","Review & save"),(d,w)->{try{
                if(generation!=ticket||!resumed||!idle())throw new IllegalStateException("STALE_CONFIRMATION");knowledge.approve(raw);show(t("已发布且本机已审核保存。返回可迁移技能页，用新参数调用已发布流程。","Published and locally reviewed. Return to portable skills and use new parameters with the published Flow."));
            }catch(Exception e){error(e);}}).show();
    }
    private void rpc(String operation,JSONObject payload,Result callback){
        if(busy){show("BUSY");return;}if(gate!=null)gate.cancel();busy=true;long generation=++ticket;client=new UserLearningClient();var request=client;
        request.start(candidate,operation,payload,getSharedPreferences("language_connection",0).getString("pairing",""),(result,failure)->handler.post(()->{
            if(generation!=ticket||isDestroyed())return;busy=false;client=null;if(failure!=null){error(failure);return;}try{callback.accept(result);}catch(Exception e){error(e);}
        }));
    }
    private void cancel(){
        ++ticket;if(client!=null)client.cancel();client=null;busy=false;if(gate!=null)gate.cancel();
        if(!attempt.isEmpty()){
            if(activeAttempt.equals(attempt)){var cancellation=activeCancellation;if(cancellation!=null)cancellation.run();activeAttempt="";activeCancellation=null;}
            try{String run=attempt;rpc("cancel_validation",new JSONObject().put("attempt_id",run),r->{attempt="";show(t("验证已取消。已经发出的动作不等于回滚；迟到回执不能发布。","Validation cancelled. Sent actions are not rolled back; late receipts cannot publish."));});}catch(Exception e){error(e);}
        }else show(t("待确认许可已撤销。","Pending confirmation revoked."));
    }
    private void show(String value){if(status!=null)status.setText(value);}
    private void error(Exception error){show("UNCONFIRMED / "+String.valueOf(error.getMessage()));}
    @Override protected void onResume(){super.onResume();resumed=true;executing=!attempt.isEmpty()&&activeAttempt.equals(attempt);}
    @Override protected void onPause(){resumed=false;if(gate!=null)gate.cancel();++ticket;if(client!=null)client.cancel();client=null;busy=false;super.onPause();}
    @Override protected void onDestroy(){handler.removeCallbacksAndMessages(null);super.onDestroy();}
}
