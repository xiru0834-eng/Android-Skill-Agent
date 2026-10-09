package edu.sydney.parameterroom;
import android.app.Activity;
import android.content.Intent;
import android.os.*;
import android.view.*;
import android.view.accessibility.AccessibilityNodeInfo;
import android.widget.*;
import org.json.*;
import java.io.FileOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.*;

/** Local parameter room; the executor cannot read this private audit journal. */
public final class ParameterRoomActivity extends Activity {
    private int light,brightness,ac,temperature;private String caseId="manual",fault="normal";
    private JSONArray events=new JSONArray();private int[] initial;
    private JSONArray requests=new JSONArray();private int commitDelayMs,generation,readBlockMs,readBlockCount,configuredReadBlockCount;private boolean pendingResume,rearmReadBlock;
    private EditText testInput;
    private LinearLayout column;private final Handler handler=new Handler(Looper.getMainLooper());
    private TextView status;
    @Override public void onCreate(Bundle b){super.onCreate(b);getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        Intent i=getIntent();
        if(i.hasExtra("initial")||i.hasExtra("caseId")||i.hasExtra("fault")||!getFileStreamPath("parameter-room-oracle.json").isFile())configure(i);
        else try{resumeSnapshot();}catch(Exception e){
            // A damaged or unknown snapshot must not be silently replaced by a clean case.
            TextView unavailable=text("Room state unavailable / 状态无法确认；未重置原记录");unavailable.setId(id("psPage"));setContentView(unavailable);
        }
    }
    private void resumeSnapshot()throws Exception {
        byte[] raw;try(var f=openFileInput("parameter-room-oracle.json");var bytes=new java.io.ByteArrayOutputStream()){
            byte[] chunk=new byte[4096];int n;while((n=f.read(chunk))!=-1){if(bytes.size()+n>1048576)throw new IllegalArgumentException("AUDIT_SIZE");bytes.write(chunk,0,n);}raw=bytes.toByteArray();
        }
        JSONObject saved=new JSONObject(new String(raw,StandardCharsets.UTF_8)),state=saved.getJSONObject("state");
        caseId=saved.getString("case_id");fault=saved.getString("fault");events=saved.getJSONArray("events");
        JSONArray start=saved.getJSONArray("initial");if(start.length()!=4)throw new IllegalArgumentException("INITIAL");initial=new int[4];
        for(int n=0;n<4;n++){if(!(start.get(n) instanceof Integer))throw new IllegalArgumentException("INITIAL_TYPE");initial[n]=start.getInt(n);}
        String lightState=state.getString("bedroom_light.power"),acState=state.getString("bedroom_ac.power");
        if(!List.of("on","off").contains(lightState)||!List.of("on","off").contains(acState))throw new IllegalArgumentException("POWER");
        if(!(state.get("bedroom_light.brightnessPercent") instanceof Integer)||!(state.get("bedroom_ac.temperatureCelsius") instanceof Integer))throw new IllegalArgumentException("VALUE_TYPE");
        light=lightState.equals("on")?1:0;ac=acState.equals("on")?1:0;brightness=state.getInt("bedroom_light.brightnessPercent");temperature=state.getInt("bedroom_ac.temperatureCelsius");
        if(brightness<0||brightness>100||temperature<16||temperature>30)throw new IllegalArgumentException("STATE_RANGE");
        String encoded=light+","+brightness+","+ac+","+temperature;
        if(!encoded.equals(getSharedPreferences("parameter_room",0).getString("state","")))throw new IllegalArgumentException("STATE_CONFLICT");
        requests=saved.optJSONArray("requests");if(requests==null)requests=new JSONArray();commitDelayMs=saved.optInt("commit_delay_ms",0);
        new DeferredCommit(++generation,0,commitDelayMs);pendingResume=false;
        for(int n=0;n<requests.length();n++)if(!requests.getJSONObject(n).has("committed_at"))pendingResume=true;
        // Process death cannot prove whether an uncommitted input is still pending.
        // Display the persisted state but do not replay or authorize another business input.
        render();
        // No audit()/prefs write here: a read-only relaunch preserves even legacy bytes.
    }
    @Override protected void onNewIntent(Intent i){super.onNewIntent(i);
        // Bringing the existing room to front must not reset its audit identity or events.
        if(i.hasExtra("initial")||i.hasExtra("caseId")||i.hasExtra("fault")){setIntent(i);configure(i);}
    }
    private void configure(Intent i){
        handler.removeCallbacksAndMessages(null);generation++;pendingResume=false;events=new JSONArray();requests=new JSONArray();caseId=i.getStringExtra("caseId")==null?UUID.randomUUID().toString():i.getStringExtra("caseId");
        fault=i.getStringExtra("fault")==null?"normal":i.getStringExtra("fault");
        commitDelayMs=i.getIntExtra("commitDelayMs",0);new DeferredCommit(generation,0,commitDelayMs);
        readBlockMs=i.getIntExtra("readBlockMs",0);readBlockCount=i.getIntExtra("readBlockCount",0);
        if(readBlockMs<0||readBlockMs>7000||readBlockCount<0||readBlockCount>4)throw new IllegalArgumentException("READ_BLOCK_RANGE");
        configuredReadBlockCount=readBlockCount;rearmReadBlock=i.getBooleanExtra("rearmReadBlock",false);
        String raw=i.getStringExtra("initial");if(raw==null)raw=getSharedPreferences("parameter_room",0).getString("state","0,40,0,20");
        String[] parts=raw.split(",");if(parts.length!=4)throw new IllegalArgumentException("INITIAL");
        initial=Arrays.stream(parts).mapToInt(Integer::parseInt).toArray();light=initial[0];brightness=initial[1];ac=initial[2];temperature=initial[3];
        if((light!=0&&light!=1)||(ac!=0&&ac!=1)||brightness<0||brightness>100||temperature<16||temperature>30)throw new IllegalArgumentException("INITIAL");
        render();audit();
    }
    private int id(String key){return getResources().getIdentifier(key,"id",getPackageName());}
    private TextView text(String label){TextView t=new TextView(this);t.setText(label);t.setTextSize(15);t.setTextColor(0xff213438);t.setPadding(0,8,0,8);return t;}
    private LinearLayout group(String name){LinearLayout box=new LinearLayout(this);box.setOrientation(1);box.addView(text(name));column.addView(box);return box;}
    private void render(){
        ScrollView scroll=new ScrollView(this);column=new LinearLayout(this);column.setOrientation(1);column.setPadding(24,16,24,24);scroll.addView(column);setContentView(scroll);
        getWindow().getDecorView().setAccessibilityDelegate(new View.AccessibilityDelegate(){
            @Override public void onInitializeAccessibilityNodeInfo(View v,AccessibilityNodeInfo info){
                if(readBlockCount>0){readBlockCount--;SystemClock.sleep(readBlockMs);}
                super.onInitializeAccessibilityNodeInfo(v,info);
            }
        });
        column.addView(text("Parameter room / 参数房间 · local App state only"));TextView page=text(pendingResume?"room_pending_unconfirmed":fault.equals("wrong_page")?"other_room":"parameter_room");page.setId(id("psPage"));column.addView(page);
        testInput=null;if(fault.equals("keyboard_only")){
            // Wait for actual window focus, not a fixed startup delay.
            // https://developer.android.com/develop/ui/views/touch-and-input/keyboard-input/visibility#show-the-soft-keyboard-reliably
            testInput=new EditText(this){
                @Override public void onWindowFocusChanged(boolean hasFocus){
                    super.onWindowFocusChanged(hasFocus);if(!hasFocus||pendingResume)return;
                    requestFocus();post(()->{
                        if(this!=testInput||!hasWindowFocus()||!isFocused()||pendingResume||ParameterRoomActivity.this.isFinishing())return;
                        ((android.view.inputmethod.InputMethodManager)getSystemService(INPUT_METHOD_SERVICE))
                            .showSoftInput(this,android.view.inputmethod.InputMethodManager.SHOW_IMPLICIT);
                    });
                }
            };
            testInput.setHint("Local safety fixture input");column.addView(testInput);
        }
        power(group("Light"),"psLightPower","bedroom_light.power",light==1);
        slider(group("Brightness"),"psBrightness","bedroom_light.brightnessPercent",0,100,brightness);
        power(group("Air conditioner"),"psAcPower","bedroom_ac.power",ac==1);
        slider(group("Temperature"),"psTemperature","bedroom_ac.temperatureCelsius",16,30,temperature);
        if(fault.equals("duplicate"))slider(group("Brightness"),"psBrightness","distractor",0,100,40);
        status=text("");status.setId(id("psStatus"));column.addView(status);update();
        Button back=new Button(this);back.setText("Back / 返回");back.setOnClickListener(v->finish());column.addView(back);
    }
    private void power(LinearLayout parent,String key,String property,boolean on){
        Switch s=new Switch(this);s.setId(id(key));s.setText(property.equals("bedroom_light.power")?"Light power / 灯开关":"AC power / 空调开关");s.setChecked(on);s.setEnabled(!pendingResume);
        s.setAccessibilityDelegate(new View.AccessibilityDelegate(){
            @Override public boolean performAccessibilityAction(View v,int action,Bundle args){
                if(commitDelayMs>0&&action==AccessibilityNodeInfo.ACTION_CLICK){boolean desired=!s.isChecked();defer(property,desired?"on":"off",()->s.setChecked(desired));return true;}
                return super.performAccessibilityAction(v,action,args);
            }
        });
        s.setOnCheckedChangeListener((button,value)->{if(property.equals("bedroom_light.power"))light=value?1:0;else ac=value?1:0;event(property,value?"on":"off");});parent.addView(s);
    }
    private void slider(LinearLayout parent,String key,String property,int min,int max,int value){
        SeekBar s=new SeekBar(this);s.setId(id(key));s.setMin(min);s.setMax(max);s.setProgress(value);
        s.setEnabled(!fault.equals("disabled")&&!pendingResume);if(fault.equals("missing")&&key.equals("psBrightness"))s.setId(id("psMissing"));
        s.setAccessibilityDelegate(new View.AccessibilityDelegate(){
            @Override public void onInitializeAccessibilityNodeInfo(View v,AccessibilityNodeInfo info){super.onInitializeAccessibilityNodeInfo(v,info);info.setClassName("android.widget.SeekBar");}
            @Override public boolean performAccessibilityAction(View v,int action,Bundle args){
                if(commitDelayMs>0&&action==AccessibilityNodeInfo.AccessibilityAction.ACTION_SET_PROGRESS.getId()){
                    int desired=(int)args.getFloat(AccessibilityNodeInfo.ACTION_ARGUMENT_PROGRESS_VALUE);
                    if(desired<min||desired>max)return false;defer(property,desired,()->s.setProgress(desired));return true;
                }
                if(action==AccessibilityNodeInfo.AccessibilityAction.ACTION_SET_PROGRESS.getId()&&key.equals("psBrightness")){
                    if(fault.equals("input_reject"))return false;
                    if(fault.equals("stubborn")){event(property,(int)args.getFloat(AccessibilityNodeInfo.ACTION_ARGUMENT_PROGRESS_VALUE));return true;}
                }return super.performAccessibilityAction(v,action,args);
            }
        });
        s.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener(){public void onStartTrackingTouch(SeekBar v){}public void onStopTrackingTouch(SeekBar v){}
            public void onProgressChanged(SeekBar v,int progress,boolean fromUser){
                if(property.equals("bedroom_light.brightnessPercent"))brightness=progress;else if(property.equals("bedroom_ac.temperatureCelsius"))temperature=progress;
                event(property,progress);
            }});parent.addView(s);
    }
    @Override protected void onResume(){super.onResume();if(rearmReadBlock)readBlockCount=configuredReadBlockCount;}
    private void defer(String property,Object value,Runnable apply){try{
        long now=SystemClock.elapsedRealtime();var ticket=new DeferredCommit(generation,now,commitDelayMs);
        JSONObject request=new JSONObject().put("property",property).put("value",value).put("requested_at",now).put("delay_ms",commitDelayMs);
        requests.put(request);audit();handler.postDelayed(new Runnable(){public void run(){
            long observedAt=SystemClock.elapsedRealtime();
            long remaining=ticket.remainingDelay(generation,observedAt);
            if(remaining<0)return;
            if(remaining>0){
                // Handler uses uptime; the audit deadline uses elapsedRealtime.
                // An early wake is pending work, not a cancelled generation.
                try{request.put("early_callbacks",request.optInt("early_callbacks",0)+1)
                    .put("last_callback_elapsed",observedAt).put("remaining_delay_ms",remaining);audit();}
                catch(Exception e){throw new IllegalStateException(e);}
                handler.postDelayed(this,remaining);return;
            }
            try{request.put("committed_at",observedAt);apply.run();audit();}catch(Exception e){throw new IllegalStateException(e);}
        }},commitDelayMs);
    }catch(Exception e){throw new IllegalStateException(e);}}
    private void event(String key,Object value){try{events.put(new JSONObject().put("property",key).put("value",value).put("ms",SystemClock.elapsedRealtime()));update();audit();}catch(Exception e){throw new IllegalStateException(e);}}
    private void update(){if(status!=null)status.setText("Light: "+(light==1?"ON":"OFF")+" · "+brightness+"%\nAC: "+(ac==1?"ON":"OFF")+" · "+temperature+"°C");}
    private void audit(){try{
        String state=light+","+brightness+","+ac+","+temperature;getSharedPreferences("parameter_room",0).edit().putString("state",state).commit();
        JSONObject snapshot=new JSONObject().put("case_id",caseId).put("fault",fault).put("initial",new JSONArray(initial)).put("events",events).put("requests",requests).put("commit_delay_ms",commitDelayMs)
            .put("state",new JSONObject().put("bedroom_light.power",light==1?"on":"off").put("bedroom_light.brightnessPercent",brightness)
                .put("bedroom_ac.power",ac==1?"on":"off").put("bedroom_ac.temperatureCelsius",temperature));
        try(FileOutputStream f=openFileOutput("parameter-room-oracle.json",MODE_PRIVATE)){f.write(snapshot.toString().getBytes(StandardCharsets.UTF_8));}
    }catch(Exception e){throw new IllegalStateException("AUDIT_STORAGE",e);}}
}
