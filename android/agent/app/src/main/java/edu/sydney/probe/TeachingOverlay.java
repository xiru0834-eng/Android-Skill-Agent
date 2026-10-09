package edu.sydney.probe;
import android.content.Intent;
import android.graphics.PixelFormat;
import android.os.*;
import android.view.*;
import android.widget.*;

/** Service-owned controls. Presentation never changes recording evidence. */
final class TeachingOverlay {
    private final ProbeService service;
    private final Handler handler=new Handler(Looper.getMainLooper());
    private LinearLayout view;
    private boolean en,recording;
    private String executionRunId="";
    private SuccessFireworksView fireworks;
    TeachingOverlay(ProbeService s){service=s;}
    private String t(String zh,String english){return en?english:zh;}
    private int dp(int v){return (int)(v*service.getResources().getDisplayMetrics().density);}
    private int id(String key){return service.getResources().getIdentifier(key,"id",service.getPackageName());}
    void showPreparation(boolean isRecording){
        remove();recording=isRecording;en=service.getSharedPreferences("language_connection",0).getBoolean("english",false);
        view=new LinearLayout(service);view.setOrientation(1);view.setPadding(dp(12),dp(8),dp(12),dp(8));view.setBackground(Ui.surface(service,UiStyle.SOFT));
        TextView title=label("prepareTitle",18),hint=label("prepareHint",14);title.setAccessibilityLiveRegion(View.ACCESSIBILITY_LIVE_REGION_POLITE);
        LinearLayout buttons=new LinearLayout(service);view.addView(buttons);
        Button start=button(buttons,"prepareStart",recording?t("开始录制","Start recording"):t("开始执行","Start execution"));Ui.button(start,true);start.setEnabled(false);
        start.setOnClickListener(v->{WorkflowPreparation p=service.workflowPreparation();if(p!=null)p.start();});
        Button back=button(buttons,"prepareCancel",t("返回取消","Cancel / return"));back.setOnClickListener(v->{service.stopAll();service.startActivity(new Intent(service,recording?TeachingActivity.class:WorkflowLibraryActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK|Intent.FLAG_ACTIVITY_CLEAR_TOP));});
        Button dock=button(buttons,"prepareDock",t("移到上方","Move to top"));
        WindowManager wm=(WindowManager)service.getSystemService(android.content.Context.WINDOW_SERVICE);
        WindowManager.LayoutParams p=new WindowManager.LayoutParams(Math.min(dp(420),service.getResources().getDisplayMetrics().widthPixels-dp(24)),-2,
            WindowManager.LayoutParams.TYPE_ACCESSIBILITY_OVERLAY,WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE,PixelFormat.TRANSLUCENT);
        p.gravity=Gravity.BOTTOM|Gravity.CENTER_HORIZONTAL;p.y=dp(12);
        dock.setOnClickListener(v->{boolean bottom=(p.gravity&Gravity.VERTICAL_GRAVITY_MASK)==Gravity.BOTTOM;p.gravity=(bottom?Gravity.TOP:Gravity.BOTTOM)|Gravity.CENTER_HORIZONTAL;dock.setText(bottom?t("移到下方","Move to bottom"):t("移到上方","Move to top"));wm.updateViewLayout(view,p);});
        wm.addView(view,p);
        handler.post(new Runnable(){public void run(){if(view==null)return;WorkflowPreparation prep=service.workflowPreparation();
            if(prep==null||!prep.active()){remove();return;}
            set(title,prep.title(en));set(hint,prep.hint(en));start.setEnabled(prep.ready());handler.postDelayed(this,250);
        }});
    }
    void show(boolean isRecording) {
        remove();recording=isRecording;en=service.getSharedPreferences("language_connection",0).getBoolean("english",false);
        executionRunId=recording?"":ExecutionResultData.latestRunId(service);
        if(recording)service.getSharedPreferences("teaching_journey",0).edit().putString("currentTrace",service.workflowRecorder().traceId()).apply();
        view=new LinearLayout(service);view.setOrientation(1);view.setPadding(dp(12),dp(8),dp(12),dp(8));view.setElevation(dp(2));
        android.graphics.drawable.GradientDrawable background=Ui.surface(service,UiStyle.SOFT);view.setBackground(background);
        TextView title=label("teachOverlayTitle",18);title.setTypeface(android.graphics.Typeface.DEFAULT,android.graphics.Typeface.BOLD);title.setAccessibilityLiveRegion(View.ACCESSIBILITY_LIVE_REGION_POLITE);
        TextView timer=label("teachOverlayTimer",14),next=label("teachOverlayNext",15),last=label("teachOverlayLast",14);last.setMaxLines(3);
        fireworks=null;
        if(!recording){fireworks=new SuccessFireworksView(service);view.addView(fireworks,new LinearLayout.LayoutParams(-1,dp(72)));fireworks.setVisibility(View.GONE);}
        LinearLayout buttons=new LinearLayout(service);view.addView(buttons);
        Button done=button(buttons,"teachOverlayFinish",t("结束录制","Finish recording"));
        Ui.button(done,true);done.setTextSize(14);done.setPadding(dp(4),dp(8),dp(4),dp(8));
        done.setOnClickListener(v->{WorkflowRecorder r=service.workflowRecorder();if(recording&&r.active()&&(!r.ready()||r.hasPending()||r.inspectingLayout()))return;finish(false);});
        Button cancel=button(buttons,"teachOverlayCancel",t("取消录制","Cancel recording"));cancel.setVisibility(recording?View.VISIBLE:View.GONE);cancel.setOnClickListener(v->finish(true));
        Button dock=button(buttons,"teachOverlayDock",t("移到上方","Move to top"));
        WindowManager wm=(WindowManager)service.getSystemService(android.content.Context.WINDOW_SERVICE);
        int width=Math.min(dp(420),service.getResources().getDisplayMetrics().widthPixels-dp(24));
        WindowManager.LayoutParams p=new WindowManager.LayoutParams(width,-2,WindowManager.LayoutParams.TYPE_ACCESSIBILITY_OVERLAY,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE,PixelFormat.TRANSLUCENT);
        p.gravity=Gravity.BOTTOM|Gravity.CENTER_HORIZONTAL;p.y=dp(12);
        dock.setOnClickListener(v->{boolean bottom=(p.gravity&Gravity.VERTICAL_GRAVITY_MASK)==Gravity.BOTTOM;p.gravity=(bottom?Gravity.TOP:Gravity.BOTTOM)|Gravity.CENTER_HORIZONTAL;
            dock.setText(bottom?t("移到下方","Move to bottom"):t("移到上方","Move to top"));wm.updateViewLayout(view,p);});
        wm.addView(view,p);
        handler.post(new Runnable(){public void run(){if(view==null)return;
            if(recording){WorkflowRecorder r=service.workflowRecorder();TeachingStatus.Data d=new TeachingStatus.Data();d.connected=true;d.selected=true;
                d.active=r.active();d.ready=r.ready();d.pending=r.hasPending();d.inspecting=r.inspectingLayout();d.steps=r.stepCount();d.end=r.end();d.error=r.error();d.flexible=r.flexible();d.savedOverview=r.savedOverview();d.routeValid=r.routeComplete();
                String kind=TeachingStatus.kind(d);set(title,TeachingStatus.title(kind,en));
                String source=r.automated()?t("自动化测试 · ","Automated test · "):"";
                set(timer,source+(d.active?TeachingStatus.clock(r.elapsedMs())+" · ":"")+d.steps+t(" 步已记录"," steps recorded"));
                set(last,d.active?(d.pending||!d.ready||d.inspecting?TeachingStatus.hint(kind,d.error,d.steps,en):t("最近确认：","Last confirmed: ")+r.lastAction(en)):TeachingStatus.hint(kind,d.error.isEmpty()?d.end:d.error,d.steps,en));
                next.setVisibility(d.active&&d.ready&&!d.pending&&!d.inspecting?View.VISIBLE:View.GONE);set(next,r.nextAction(en));
                done.setText(d.active?t("结束录制","Finish recording"):t("查看结果","View result"));done.setEnabled(!d.active||(d.ready&&!d.pending&&!d.inspecting));cancel.setVisibility(d.active?View.VISIBLE:View.GONE);
                background.setColor(kind.equals("ERROR")||kind.equals("INCOMPLETE")?0xffffeedb:0xffe5f1ec);
            }else{
                boolean active=service.workflowRunning();done.setText(active?t("停止并返回","Stop / return"):t("查看结果","View result"));
                ExecutionResultData result=ExecutionResultData.read(service,executionRunId);
                String status=result!=null&&result.valid?result.status:"";
                if(!active&&ExecutionCelebration.claim(service,result,executionRunId)){fireworks.setVisibility(View.VISIBLE);fireworks.play();}
                set(title,active?t("正在执行已审核流程","Executing reviewed workflow"):status.equals("SUCCEEDED")?t("目标已核验","Targets verified"):t("未确认完成","Completion not confirmed"));
                timer.setVisibility(View.GONE);next.setVisibility(View.GONE);set(last,t("仅限实验 App，可随时停止。","Experiment only. You can stop at any time."));
            }
            handler.postDelayed(this,250);
        }});
    }
    private TextView label(String key,int size){TextView v=new TextView(service);v.setId(id(key));v.setTextColor(0xff173a2e);v.setTextSize(size);v.setPadding(0,dp(2),0,dp(2));view.addView(v);return v;}
    private Button button(LinearLayout parent,String key,String label){Button b=new Button(service);b.setId(id(key));b.setText(label);Ui.button(b,false);b.setTextSize(14);b.setPadding(dp(4),dp(8),dp(4),dp(8));LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(0,-2,1);p.setMargins(dp(2),dp(6),dp(2),0);parent.addView(b,p);return b;}
    private void set(TextView view,String value){if(!value.contentEquals(view.getText()))view.setText(value);}
    private void finish(boolean cancel) {
        if(cancel)service.workflowRecorder().stop("CANCELLED");
        service.stopAll();remove();
        Intent destination=ExecutionResultPolicy.destination(recording)==ExecutionResultPolicy.Destination.RECORDING_REVIEW?
            new Intent(service,TeachingActivity.class):ExecutionResultActivity.intent(service,executionRunId);
        service.startActivity(destination.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK|Intent.FLAG_ACTIVITY_CLEAR_TOP));
    }
    void remove(){handler.removeCallbacksAndMessages(null);if(fireworks!=null){fireworks.stop();fireworks=null;}if(view!=null){try{((WindowManager)service.getSystemService(android.content.Context.WINDOW_SERVICE)).removeView(view);}catch(RuntimeException ignored){}view=null;}}
}
