package edu.sydney.probe;
import android.app.*;
import android.content.*;
import android.os.*;
import android.widget.*;
import org.json.*;

/** Explicit review, unchanged-byte transfer, semantic preview, then current-device execution. */
public final class PortableSkillActivity extends Activity {
    private PortableSkillStore store;private TextView status;private EditText input,local;
    private boolean en,busy;private long ticket;private WorkflowSelectionClient.Request request;
    private final Handler handler=new Handler(Looper.getMainLooper());
    private String t(String zh,String english){return en?english:zh;}
    @Override protected void onCreate(Bundle state){super.onCreate(state);store=new PortableSkillStore(this);en=getSharedPreferences("language_connection",0).getBoolean("english",false);draw();}
    private void draw(){
        var page=Ui.page(this);Ui.toolbar(page,t("可迁移参数技能","Portable parameter skills"),"portableLanguage",en?"中文":"English",()->{cancelRequest();en=!en;getSharedPreferences("language_connection",0).edit().putBoolean("english",en).apply();draw();},"portableBack",t("返回","Back"),this::finish);
        Ui.label(page,t("灯开关 / 亮度 · 空调开关 / 温度","Light power / brightness · AC power / temperature"),20);
        Ui.label(page,t("参数房间实验入口。预定义语义与绑定，不是任意 App 自动学习。导入包不继承原设备授权。","Parameter-room experiment. Predefined semantics and bindings, not arbitrary App learning. Imports do not inherit source-device permission."),14);
        Ui.action(page,"portableTemplate",t("核对实验房间技能","Review room skills"),()->reviewTemplate(),false);
        Ui.action(page,"portableImport",t("导入操作包","Import package"),()->{if(idle())startActivityForResult(new Intent(Intent.ACTION_OPEN_DOCUMENT).setType("application/json").addCategory(Intent.CATEGORY_OPENABLE),1);},false);
        Ui.action(page,"portableIncoming",t("核对 USB 暂存包","Review USB-staged package"),()->{if(idle())try{review(store.incoming());}catch(Exception e){error(e);}},false);
        Ui.action(page,"portableExport",t("导出已审核操作包","Export reviewed package"),()->{if(idle())try{store.approved();startActivityForResult(new Intent(Intent.ACTION_CREATE_DOCUMENT).setType("application/json").putExtra(Intent.EXTRA_TITLE,"parameter-skill.json"),2);}catch(Exception e){error(e);}},false);
        input=new EditText(this);input.setId(id("portableInput"));input.setHint(t("开灯，把亮度调到50%，空调设为26度","Turn on the light, set brightness to 50%, set AC to 26 degrees"));Ui.field(input);page.addView(input);
        Ui.action(page,"portableUnderstand",t("GPT 理解并预览","Understand & preview with GPT"),this::understand,true);
        Ui.label(page,t("已发布流程 · 可跨会话复用","Published Flows · reusable across sessions"),18);
        Ui.action(page,"learningEntry",t("学习新流程（示范 / 资料）","Learn a new Flow (demonstration / document)"),()->{if(idle())startActivity(new Intent(this,UserLearningActivity.class));},false);
        Ui.label(page,t("从已发布知识中选择，不重新生成。新设备需本机审核；确认后才执行。","Select from published knowledge, not regenerate. Review on this device; execute only after confirmation."),14);
        Ui.action(page,"publishedFlowReview",t("审核已发布流程包","Review published Flow package"),this::reviewFlow,false);
        Ui.action(page,"publishedFlowImport",t("从文件导入已发布流程","Import published Flow from file"),()->{if(idle())startActivityForResult(new Intent(Intent.ACTION_OPEN_DOCUMENT).setType("application/json").addCategory(Intent.CATEGORY_OPENABLE),3);},false);
        Ui.action(page,"publishedFlowExport",t("导出已审核流程包","Export locally reviewed Flow"),()->{if(idle())try{new FlowKnowledgeStore(this).approved();startActivityForResult(new Intent(Intent.ACTION_CREATE_DOCUMENT).setType("application/json").putExtra(Intent.EXTRA_TITLE,"published-flow.json"),4);}catch(Exception e){error(e);}},false);
        Ui.action(page,"publishedFlowUnderstand",t("用上方输入调用已发布流程","Use input above with published Flow"),this::understandFlow,true);
        Ui.label(page,t("未提及的属性保持不变。确认之前不操作。","Unmentioned properties stay unchanged. No input before confirmation."),14);
        local=new EditText(this);local.setId(id("portableCalls"));local.setHint(t("实验：结构化 calls JSON（不调用 GPT）","Experiment: structured calls JSON (no GPT)"));Ui.field(local);page.addView(local);
        Ui.action(page,"portableStructured",t("实验：预览结构化调用","Experiment: preview structured calls"),()->{if(idle())try{preview(store.approved(),new JSONArray(local.getText().toString()));}catch(Exception e){error(e);}},false);
        Ui.action(page,"portableStop",t("取消 / 停止","Cancel / Stop"),()->{cancelRequest();if(ProbeService.current()!=null)ProbeService.current().stopAll();show("UNCONFIRMED / CANCELLED\n"+t("已取消，迟到响应不能执行。","Cancelled; late responses cannot execute."));},false);
        status=Ui.label(page,"",15);status.setId(id("portableStatus"));Ui.notice(status);status.setAccessibilityLiveRegion(android.view.View.ACCESSIBILITY_LIVE_REGION_POLITE);
        refresh();
    }
    private int id(String name){return getResources().getIdentifier(name,"id",getPackageName());}
    private boolean idle(){ProbeService service=ProbeService.current();return !busy&&!UserLearningSession.active()&&(service==null||(!service.workflowRunning()&&!service.workflowPreparing()&&!service.workflowRecorder().active()));}
    private void reviewTemplate(){if(idle())try{review(PortableSkillCodec.template());}catch(Exception e){error(e);}}
    private void review(String raw)throws Exception {
        var pkg=PortableSkillCodec.decode(raw);store.version();long generation=++ticket;
        new AlertDialog.Builder(this).setTitle(t("核对能力与绑定","Review capabilities & bindings")).setMessage(new JSONObject(pkg.raw).toString(2)+"\nSHA256: "+pkg.hash)
            .setNegativeButton(t("取消","Cancel"),null).setPositiveButton(t("确认保存","Save"),(d,w)->{try{
                if(generation!=ticket||!idle())throw new IllegalStateException("STALE_CONFIRMATION");store.approve(raw);refresh();
            }catch(Exception e){error(e);}}).show();
    }
    private void understand(){if(!idle())return;try{
        var pkg=store.approved();String text=SemanticParameterCodec.text(input.getText().toString(),2000);long generation=++ticket;busy=true;
        request=new WorkflowSelectionClient.Request(text,pkg.catalog,getSharedPreferences("language_connection",0).getString("pairing",""),WorkflowSelectionClient.Kind.SEMANTIC);
        var current=request;show(t("正在理解，尚未执行…","Understanding; nothing executed…"));
        current.start((response,failure)->handler.post(()->{if(generation!=ticket||isDestroyed())return;busy=false;request=null;
            try{current.assertCurrent();if(failure!=null)throw failure;if(!text.equals(input.getText().toString())||!pkg.hash.equals(store.approved().hash))throw new IllegalStateException("STALE_REQUEST");
                String outcome=response.getString("status");show((outcome.equals("invoke")?"PREVIEW":outcome.equals("clarify")?"CLARIFY":"REJECTED")+" / "+response.getString("message"));if(outcome.equals("invoke"))preview(pkg,response.getJSONArray("calls"));
            }catch(Exception e){error(e);}}));
        handler.postDelayed(()->{if(generation==ticket&&busy){cancelRequest();show("UNCONFIRMED / SELECTION_DEADLINE");}},current.deadlineMillis());
    }catch(Exception e){cancelRequest();error(e);}}
    private void reviewFlow(){if(!idle())return;try{reviewFlow(new FlowKnowledgeStore(this).incoming());}catch(Exception e){error(e);}}
    private void reviewFlow(String raw){if(!idle())return;try{
        var knowledge=new FlowKnowledgeStore(this);var data=knowledge.decode(raw);long generation=++ticket;
        new AlertDialog.Builder(this).setTitle(t("本机审核，不继承授权","Local review, no inherited rights"))
            .setMessage(data.getJSONArray("catalog").toString(2)+"\n"+t("实际验证点不是完整参数域保证。此处只审核保存知识，不执行；不会复制原设备授权。","Observed points are not full-domain verification. Review and save only; no execution or inherited source-device rights."))
            .setNegativeButton(t("取消","Cancel"),null).setPositiveButton(t("确认保存","Save"),(d,w)->{try{if(generation!=ticket||!idle())throw new IllegalArgumentException("STALE_CONFIRMATION");knowledge.approve(raw);show(t("已保存本机审核的已发布流程，可输入调用。","Published Flow reviewed locally. Enter a task to use it."));}catch(Exception e){error(e);}}).show();
    }catch(Exception e){error(e);}}
    private void understandFlow(){if(!idle())return;try{
        var knowledge=new FlowKnowledgeStore(this);var data=knowledge.approved();String snapshot=data.toString();
        String text=SemanticParameterCodec.text(input.getText().toString(),2000);long generation=++ticket;busy=true;
        request=new WorkflowSelectionClient.Request(text,data.getJSONArray("catalog"),getSharedPreferences("language_connection",0).getString("pairing",""),WorkflowSelectionClient.Kind.FLOW);
        var current=request;show(t("正在选择已发布流程，尚未执行…","Selecting a published Flow; not executing…"));
        current.start((response,failure)->handler.post(()->{if(generation!=ticket||isDestroyed())return;busy=false;request=null;
            try{current.assertCurrent();if(failure!=null)throw failure;if(!text.equals(input.getText().toString())||!snapshot.equals(knowledge.approved().toString()))throw new IllegalArgumentException("STALE_REQUEST");
                String outcome=response.getString("status");knowledge.write("flow-user-selection.json",response.toString());
                show((outcome.equals("invoke")?"PREVIEW":outcome.equals("clarify")?"CLARIFY":"REJECTED")+" / "+response.getString("message"));
                if(outcome.equals("invoke"))previewFlow(knowledge,data,knowledge.validateResponse(data,response));
            }catch(Exception e){error(e);}}));
        handler.postDelayed(()->{if(generation==ticket&&busy){cancelRequest();show("UNCONFIRMED / SELECTION_DEADLINE");}},current.deadlineMillis());
    }catch(Exception e){cancelRequest();error(e);}}
    private void previewFlow(FlowKnowledgeStore knowledge,JSONObject data,JSONObject plan)throws Exception{
        String snapshot=data.toString();long generation=++ticket;var gate=new PortableConfirmationGate();
        AlertDialog dialog=new AlertDialog.Builder(this).setTitle(t("确认流程与本次修改","Confirm Flow and this task's changes"))
            .setMessage(data.getJSONObject("flow").getString("id")+" @ "+data.getJSONObject("flow").getString("version")+"\n"+plan.getJSONArray("steps").toString(2)+"\n"+t("只改已列出的属性；其他属性保持。整体执行上限8秒，失败不自动重发。","Only listed properties change; others stay unchanged. Whole execution: 8 seconds, no automatic resend."))
            .setNegativeButton(t("取消","Cancel"),null).setPositiveButton(t("确认执行","Run"),(d,w)->gate.confirm()).create();
        dialog.setOnCancelListener(d->gate.cancel());dialog.setOnDismissListener(d->{if(!gate.dismiss())return;try{
            if(generation!=ticket||!idle()||isDestroyed()||isFinishing()||!snapshot.equals(knowledge.approved().toString()))throw new IllegalArgumentException("STALE_CONFIRMATION");
            var service=ProbeService.current();if(service==null)throw new IllegalArgumentException("SERVICE_OFF");
            java.util.Set<String> writes=new java.util.TreeSet<>();var a=plan.getJSONArray("actual_write_set");for(int i=0;i<a.length();i++)writes.add(a.getString(i));
            service.runFlow(plan,writes,"PUBLISHED_USER_TASK",result->{try{knowledge.write("flow-user-result.json",result.toString());handler.post(()->{if(!isDestroyed())show(flowSummary(result,false));});}catch(Exception e){handler.post(()->error(e));}});
        }catch(Exception e){error(e);}});dialog.show();
    }
    private void preview(PortableSkillCodec.Package pkg,JSONArray proposed)throws Exception {
        pkg.compile(proposed);String snapshot=proposed.toString();long generation=++ticket;
        var gate=new PortableConfirmationGate();
        AlertDialog dialog=new AlertDialog.Builder(this).setTitle(t("确认技能 + 参数","Confirm skills + parameters")).setMessage(snapshot+"\n"+t("将在参数房间执行并核验；只改变实验 App 状态。","Execute and verify in the parameter room; local experimental App state only."))
            .setNegativeButton(t("取消","Cancel"),null).setPositiveButton(t("确认执行","Run"),(d,w)->gate.confirm()).create();
        dialog.setOnCancelListener(d->gate.cancel());
        dialog.setOnDismissListener(d->{if(!gate.dismiss())return;try{
                if(generation!=ticket||isDestroyed()||isFinishing()||!idle()||!pkg.hash.equals(store.approved().hash))throw new IllegalStateException("STALE_CONFIRMATION");
                ProbeService service=ProbeService.current();if(service==null)throw new IllegalStateException("SERVICE_OFF");
                service.runPortable(pkg,new JSONArray(snapshot),result->{try{store.write("portable-result.json",result.toString());handler.post(()->{if(!isDestroyed())show(result.toString());});}catch(Exception e){handler.post(()->error(e));}});
            }catch(Exception e){error(e);}});
        dialog.show();
    }
    private void refresh(){try{var pkg=store.approved();show(t("已审核，可复用。包指纹：","Reviewed and reusable. Package hash: ")+pkg.hash);
        try(var f=openFileInput("portable-result.json")){show(status.getText()+"\n\n"+t("上一次执行记录（不是本次指令结果）：","Previous execution (not this request's result):")+"\n"+SkillFiles.read(f,262144));}catch(java.io.FileNotFoundException ignored){}
        try(var f=openFileInput("flow-user-result.json")){show(flowSummary(new JSONObject(SkillFiles.read(f,262144)),true));}catch(java.io.FileNotFoundException ignored){}
    }catch(Exception e){show(t("尚无有效的本机审核；请先核对或导入技能。","No valid local review. Review or import skills first.")+"\n"+e.getMessage());}}
    private void show(String value){if(status!=null)status.setText(value);}
    private String flowSummary(JSONObject result,boolean historical){return (historical?t("上次流程结果（不是新指令结果）","Previous Flow result (not a new task)"):t("本次流程结果","Flow task result"))+"\n"+result.optString("final_status","UNCONFIRMED")+"\n"+t("已核验步骤：","Verified steps: ")+result.optInt("completed_steps")+"\n"+t("实际观察状态：","Observed state: ")+result.optJSONObject("final_observed_state")+"\n"+t("完整回执已保存在本机。","Full receipt saved locally.");}
    private void error(Exception e){show(PortableEntryPolicy.display(e));}
    private void cancelRequest(){ticket++;if(request!=null)request.cancel();request=null;busy=false;handler.removeCallbacksAndMessages(null);}
    @Override protected void onPause(){cancelRequest();super.onPause();}
    @Override protected void onResume(){super.onResume();if(status!=null)refresh();}
    @Override protected void onActivityResult(int code,int result,Intent data){super.onActivityResult(code,result,data);if(result!=RESULT_OK||data==null||data.getData()==null)return;
        try{if(code==1){try(var f=getContentResolver().openInputStream(data.getData())){review(SkillFiles.read(f,24000));}}
            else if(code==2){var pkg=store.approved();try(var f=getContentResolver().openOutputStream(data.getData(),"wt")){if(f==null)throw new IllegalStateException("EXPORT_STORAGE");f.write(pkg.raw.getBytes(java.nio.charset.StandardCharsets.UTF_8));}show(t("已导出：不含密钥、设备坐标和授权。","Exported: no credentials, device coordinates or approval."));}
            else if(code==3){if(!idle())throw new IllegalStateException("BUSY");try(var f=getContentResolver().openInputStream(data.getData())){if(f==null)throw new IllegalStateException("IMPORT_STORAGE");reviewFlow(SkillFiles.read(f,131072));}}
            else if(code==4){if(!idle())throw new IllegalStateException("BUSY");String raw=new FlowKnowledgeStore(this).approvedRaw();try(var f=getContentResolver().openOutputStream(data.getData(),"wt")){if(f==null)throw new IllegalStateException("EXPORT_STORAGE");f.write(raw.getBytes(java.nio.charset.StandardCharsets.UTF_8));}show(t("已导出流程知识；不附带本机审核许可。","Flow knowledge exported; local approval is not transferred."));}}
        catch(Exception e){error(e);}}
}
