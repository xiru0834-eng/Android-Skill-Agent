package edu.sydney.probe;
import android.app.*;
import android.content.*;
import android.os.*;
import android.util.Base64;
import android.view.accessibility.AccessibilityNodeInfo;
import android.widget.*;
import org.json.*;
import java.nio.charset.StandardCharsets;

/** Evaluator drives the SAME normal UI; no fixture execution and no oracle here. */
public final class PublishedFlowUiChecks extends Instrumentation {
    private Bundle args;private UiAutomation ui;
    @Override public void onCreate(Bundle args){super.onCreate(args);this.args=args;start();}
    private int id(String name){return getTargetContext().getResources().getIdentifier(name,"id","edu.sydney.probe");}
    private void click(Activity a,String name){runOnMainSync(()->{var v=a.findViewById(id(name));if(v==null||!v.performClick())throw new IllegalArgumentException("UI_CONTROL_UNAVAILABLE:"+name);});}
    private String read(String name){try(var f=getTargetContext().openFileInput(name)){return SkillFiles.read(f,262144);}catch(Exception e){return "";}}
    private boolean dialogClick(String zh,String en,long deadline){
        while(SystemClock.elapsedRealtime()<deadline){
            var root=ui.getRootInActiveWindow();if(root!=null){try{
                for(String label:new String[]{zh,en})for(var n:root.findAccessibilityNodeInfosByText(label)){
                    if(n.getClassName()!=null&&n.getClassName().toString().equals("android.widget.Button")&&n.isClickable()&&n.performAction(AccessibilityNodeInfo.ACTION_CLICK))return true;
                }
            }finally{root.recycle();}}SystemClock.sleep(50);
        }return false;
    }
    @Override public void onStart(){Bundle out=new Bundle();final PortableSkillActivity[] shownPage={null};try{
        ui=getUiAutomation(UiAutomation.FLAG_DONT_SUPPRESS_ACCESSIBILITY_SERVICES);
        // Instrumentation restarts the target process. The external evaluator
        // reconnects the SAME enabled service; never substitute a fake service.
        Bundle phase=new Bundle();phase.putString("phase","WAIT_REAL_SERVICE");sendStatus(0,phase);
        long bindDeadline=SystemClock.elapsedRealtime()+15000;
        while(ProbeService.current()==null&&SystemClock.elapsedRealtime()<bindDeadline)SystemClock.sleep(50);
        if(ProbeService.current()==null)throw new IllegalArgumentException("REAL_SERVICE_NOT_CONNECTED");
        // Enter via the existing launcher and existing navigation button.
        var main=startActivitySync(new Intent(getTargetContext(),MainActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
        var monitor=addMonitor(PortableSkillActivity.class.getName(),null,false);click(main,"portableEntry");
        var page=(PortableSkillActivity)waitForMonitorWithTimeout(monitor,5000);removeMonitor(monitor);
        if(page==null)throw new IllegalArgumentException("NORMAL_ENTRY_NOT_OPENED");
        shownPage[0]=page;
        if(Boolean.parseBoolean(args.getString("review","false"))){
            click(page,"publishedFlowReview");if(!dialogClick("确认保存","Save",SystemClock.elapsedRealtime()+5000))throw new IllegalArgumentException("REVIEW_DIALOG_MISSING");
        }
        String text=new String(Base64.decode(args.getString("text64"),Base64.DEFAULT),StandardCharsets.UTF_8);
        String oldSelection=read("flow-user-selection.json"),oldResult=read("flow-user-result.json");
        runOnMainSync(()->((EditText)page.findViewById(id("portableInput"))).setText(text));
        click(page,"publishedFlowUnderstand");long until=SystemClock.elapsedRealtime()+24000;
        if(Boolean.parseBoolean(args.getString("cancel","false"))){
            SystemClock.sleep(100);click(page,"portableStop");SystemClock.sleep(1000);
            out.putString("cancel_status","USER_CANCELLED");
        }else{
            JSONObject selection=null;
            while(SystemClock.elapsedRealtime()<until){String raw=read("flow-user-selection.json");if(!raw.equals(oldSelection)&&!raw.isEmpty()){selection=new JSONObject(raw);break;}SystemClock.sleep(50);}
            if(selection==null)throw new IllegalArgumentException("NORMAL_UI_SELECTION_NOT_RETURNED");
            out.putString("selection",selection.toString());
            if(selection.getString("status").equals("invoke")){
                if(!dialogClick("确认执行","Run",SystemClock.elapsedRealtime()+3000))throw new IllegalArgumentException("TASK_CONFIRMATION_MISSING");
                until=SystemClock.elapsedRealtime()+13000;String result="";
                while(SystemClock.elapsedRealtime()<until){result=read("flow-user-result.json");if(!result.equals(oldResult)&&!result.isEmpty())break;SystemClock.sleep(50);}
                if(result.isEmpty()||result.equals(oldResult))throw new IllegalArgumentException("USER_RESULT_MISSING");out.putString("result",result);
                // Normal return opens the user-visible persisted result, explicitly historical.
                var shown=startActivitySync(new Intent(getTargetContext(),PortableSkillActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
                final String[] visible={""};runOnMainSync(()->visible[0]=((TextView)shown.findViewById(id("portableStatus"))).getText().toString());out.putString("visible_result",visible[0]);
            }
        }
        out.putString("channel","EVALUATOR_UI_ACTION_NORMAL_PRODUCT_ENTRY");out.putString("text",text);finish(-1,out);
    }catch(Throwable e){out.putString("error",e.toString());if(shownPage[0]!=null)runOnMainSync(()->out.putString("visible_error",((TextView)shownPage[0].findViewById(id("portableStatus"))).getText().toString()));finish(1,out);}}
}
