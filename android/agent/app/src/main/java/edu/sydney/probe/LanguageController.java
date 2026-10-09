package edu.sydney.probe;

import android.content.Intent;
import android.graphics.PixelFormat;
import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;
import android.view.Gravity;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;
import org.json.JSONObject;
import java.util.List;

/** Service-owned invocation lifecycle; model output never bypasses the saved approval. */
public final class LanguageController {
    private final ProbeService service;
    private final Handler handler=new Handler(Looper.getMainLooper());
    private final WindowManager windows;
    private LinearLayout overlay;
    private TextView overlayText;
    private long generation,started;
    private String requestId="",snapshot="",runId="";
    private boolean busy,networkPending;
    public String phase="IDLE",message="输入指令，然后执行 / Enter a command",interpreted="";
    private static final String PKG=ProbePolicy.TRANSFER_PACKAGE;
    public LanguageController(ProbeService service) {
        this.service=service;windows=(WindowManager)service.getSystemService(android.content.Context.WINDOW_SERVICE);
    }
    public boolean busy() { return busy; }
    public boolean understanding() { return busy && "UNDERSTANDING".equals(phase); }
    private TwoStepSkill approved() {
        TwoStepSkill s=new TwoStepStore(service).load(PKG);
        if(s==null || !s.steps.get(0).resourceId.equals(PKG+":id/mainToggle")
                || !s.steps.get(1).resourceId.equals(PKG+":id/otherToggle"))
            throw new IllegalArgumentException("请先审核阅读灯/风扇技能 / Review the lamp/fan skill first");
        return s;
    }
    public void submit(String text,String pairing) {
        if(busy || networkPending) { message="请等待上一请求结束 / Previous request is still pending";return; }
        if(text==null || text.isBlank() || text.length()>500) { message="请输入 1–500 字符 / Enter 1–500 characters";return; }
        if(pairing==null || !pairing.matches("[a-f0-9]{48}")) { message="请先设置电脑配对码 / Set the pairing code";return; }
        try { snapshot=TwoStepCodec.encode(approved()); }
        catch(RuntimeException e) { message=e.getMessage();return; }
        service.stopAll();removeOverlay();busy=true;networkPending=true;runId="";interpreted="";
        started=SystemClock.elapsedRealtime();requestId=java.util.UUID.randomUUID().toString().replace("-","");
        long ticket=++generation;String id=requestId;
        update("UNDERSTANDING","GPT 正在理解 / Interpreting with GPT");
        handler.postDelayed(() -> { if(valid(ticket) && understanding()) cancel(); },55000);
        new Thread(() -> {
            try {
                LanguageDecision decision=LanguageClient.request(id,text,pairing);
                handler.post(() -> { networkPending=false;if(valid(ticket)) receive(ticket,decision); });
            } catch(Exception e) {
                String code=e instanceof IllegalArgumentException?e.getMessage():"NETWORK_OR_RESPONSE_ERROR";
                handler.post(() -> { networkPending=false;if(valid(ticket)) finish("ERROR","未执行 / No action: "+code); });
            }
        },"intent-request").start();
    }
    private boolean valid(long ticket) { return busy && ticket==generation && ProbeService.current()==service; }
    private void receive(long ticket,LanguageDecision decision) {
        if(!"invoke".equals(decision.status)) { finish(decision.status.toUpperCase(),decision.message);return; }
        try {
            if(!snapshot.equals(TwoStepCodec.encode(approved()))) throw new IllegalArgumentException("Approval changed");
            interpreted="阅读灯 / Lamp: "+target(decision.lamp)+"\n风扇 / Fan: "+target(decision.fan);
            showOverlay();update("OPENING","正在打开实验 App / Opening experiment App");
            Intent launch=service.getPackageManager().getLaunchIntentForPackage(PKG);
            if(launch==null) throw new IllegalArgumentException("App missing");
            service.startActivity(launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK|Intent.FLAG_ACTIVITY_REORDER_TO_FRONT));
            handler.postDelayed(() -> { if(valid(ticket)) dispatch(ticket,decision); },900);
        } catch(RuntimeException e) { finish("REFUSED","未执行：技能、App 或停止入口不可用 / Cannot safely start"); }
    }
    private String target(Boolean b) { return b==null?"保持不变 / Keep":b?"开启 / ON":"关闭 / OFF"; }
    private void dispatch(long ticket,LanguageDecision decision) {
        try {
            TwoStepSkill skill=approved();
            if(!snapshot.equals(TwoStepCodec.encode(skill))) throw new IllegalArgumentException("Approval changed");
            TwoStepRunner.Observation observed=TwoStepRunner.read(service,skill);
            String reason=TwoStepEngine.bindingReason(skill,observed.scenes);
            if(!"READY".equals(reason)) { finish("REFUSED","没有操作 / No action: "+reason);return; }
            List<Boolean> desired=decision.resolve(observed.scenes.get(0).checked,observed.scenes.get(1).checked);
            service.runTwo(skill,desired);
            runId=new JSONObject(new SkillStore(service).result()).getString("runId");
            update("EXECUTING","正在执行并核验 / Executing and verifying");
            poll(ticket,SystemClock.elapsedRealtime());
        } catch(Exception e) { service.stopAll();finish("UNCONFIRMED","无法确认执行 / Execution not confirmed"); }
    }
    private void poll(long ticket,long executionStart) {
        if(!valid(ticket)) return;
        try {
            JSONObject report=new JSONObject(new SkillStore(service).result());
            if(!runId.equals(report.getString("runId"))) { service.stopAll();finish("UNCONFIRMED","运行记录已改变 / Run changed");return; }
            String status=report.getString("status");
            if(!"RUNNING".equals(status)) {
                finish(status,"SUCCEEDED".equals(status)?"已核验完成 / Verified complete":
                    "未确认完成 / Not confirmed: "+report.optString("reason"));return;
            }
            if(SystemClock.elapsedRealtime()-executionStart>5000) { service.stopAll();finish("UNCONFIRMED","执行超时 / Execution timeout");return; }
            handler.postDelayed(() -> poll(ticket,executionStart),120);
        } catch(Exception e) { service.stopAll();finish("UNCONFIRMED","运行状态不可读 / Cannot read run status"); }
    }
    public void cancel() {
        if(busy) { generation++;service.stopAll();finish("CANCELLED","已停止后续操作；已发送的动作可能生效 / Stopped, not undone"); }
    }
    private void finish(String phase,String message) { busy=false;handler.removeCallbacksAndMessages(null);update(phase,message); }
    private void update(String phase,String message) {
        this.phase=phase;this.message=message;
        if(overlayText!=null) overlayText.setText(LanguageText.message(message,english()));
        try {
            JSONObject log=new JSONObject().put("requestId",requestId).put("phase",phase).put("message",message)
                .put("interpreted",interpreted).put("runId",runId).put("elapsedMs",SystemClock.elapsedRealtime()-started);
            service.getSharedPreferences("language_result",0).edit().putString("last",log.toString()).apply();
        } catch(Exception ignored) { /* User display remains available if diagnostic serialization fails. */ }
    }
    private void showOverlay() {
        removeOverlay();overlay=new LinearLayout(service);overlay.setOrientation(1);overlay.setPadding(16,8,16,8);
        overlay.setBackgroundColor(0xffeef5f3);overlayText=new TextView(service);overlayText.setTextColor(0xff18352b);
        overlay.addView(overlayText);LinearLayout buttons=new LinearLayout(service);overlay.addView(buttons);
        Button stop=new Button(service);stop.setText(english()?"STOP":"停止");stop.setOnClickListener(v->cancel());buttons.addView(stop);
        Button back=new Button(service);back.setText(english()?"Return":"返回");back.setOnClickListener(v->{cancel();removeOverlay();
            service.startActivity(new Intent(service,LanguageActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK|Intent.FLAG_ACTIVITY_REORDER_TO_FRONT));});buttons.addView(back);
        WindowManager.LayoutParams p=new WindowManager.LayoutParams(WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.WRAP_CONTENT,WindowManager.LayoutParams.TYPE_ACCESSIBILITY_OVERLAY,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE,PixelFormat.TRANSLUCENT);
        p.gravity=Gravity.BOTTOM|Gravity.CENTER_HORIZONTAL;p.y=48;windows.addView(overlay,p);
    }
    public void removeOverlay() { if(overlay!=null) { try {windows.removeView(overlay);} catch(RuntimeException ignored) {} overlay=null;overlayText=null; } }
    private boolean english() { return service.getSharedPreferences("language_connection",0).getBoolean("english",false); }
    public void close() { cancel();generation++;handler.removeCallbacksAndMessages(null);removeOverlay(); }
}
