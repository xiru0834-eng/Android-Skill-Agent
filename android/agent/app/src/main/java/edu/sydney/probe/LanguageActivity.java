package edu.sydney.probe;

import android.app.Activity;
import android.os.Bundle;
import android.os.Handler;
import android.text.InputType;
import android.text.InputFilter;
import android.view.View;
import android.view.inputmethod.InputMethodManager;
import android.widget.*;

/** User-facing bilingual entry. The original teaching/review screens remain unchanged. */
public final class LanguageActivity extends Activity {
    private final Handler handler=new Handler();
    private EditText command,pairing;
    private TextView status,summary,title,scope,inputLabel,privacy;
    private Button execute,stop,exampleZh,exampleEn,setup,back,language;
    private boolean english;
    private LinearLayout column;
    private final Runnable refresh=new Runnable() { public void run() { render();handler.postDelayed(this,250); } };
    @Override public void onCreate(Bundle saved) {
        super.onCreate(saved);english=getSharedPreferences("language_connection",0).getBoolean("english",false);
        ScrollView scroll=new ScrollView(this);column=new LinearLayout(this);column.setOrientation(1);
        int p=(int)(20*getResources().getDisplayMetrics().density);column.setPadding(p,p,p,p);
        column.setBackgroundColor(0xfff5f7f6);scroll.addView(column);setContentView(scroll);
        language=button("languageToggle","",()->{english=!english;getSharedPreferences("language_connection",0).edit().putBoolean("english",english).apply();localize();render();});
        title=text("");title.setTextSize(25);
        scope=text("");inputLabel=text("");
        command=new EditText(this);command.setId(id("languageInput"));command.setMinLines(3);
        command.setGravity(android.view.Gravity.TOP);command.setHint("例如：打开阅读灯，关闭风扇\nTurn on the lamp and turn off the fan");
        command.setInputType(InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_FLAG_MULTI_LINE);
        command.setFilters(new InputFilter[]{new InputFilter.LengthFilter(500)});column.addView(command);
        exampleZh=button("languageExampleZh","填入中文示例 / Chinese example",()->command.setText("打开阅读灯，关闭风扇"));
        exampleEn=button("languageExampleEn","填入英文示例 / English example",()->command.setText("Turn off the reading lamp and turn on the desk fan."));
        execute=button("languageExecute","执行 / Execute",this::submit);
        stop=button("languageStop","停止 / Stop",()->{LanguageController c=controller();if(c!=null)c.cancel();render();});
        status=text("");status.setId(id("languageStatus"));status.setAccessibilityLiveRegion(View.ACCESSIBILITY_LIVE_REGION_POLITE);
        summary=text("");summary.setId(id("languageSummary"));
        privacy=text("");
        setup=button("languageSetup","电脑连接设置 / Connection setup",()->pairing.setVisibility(pairing.getVisibility()==View.VISIBLE?View.GONE:View.VISIBLE));
        pairing=new EditText(this);pairing.setId(id("languagePairing"));pairing.setHint("电脑配对码（不是 API Key）/ Pairing code, not API key");
        pairing.setInputType(InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_PASSWORD);
        pairing.setSingleLine(true);pairing.setFilters(new InputFilter[]{new InputFilter.LengthFilter(48)});
        pairing.setText(getSharedPreferences("language_connection",0).getString("pairing",""));column.addView(pairing);
        if(pairing.length()>0) pairing.setVisibility(View.GONE);
        back=button("languageBack","",()->{LanguageController c=controller();if(c!=null)c.cancel();finish();});
        localize();
        if(saved!=null) command.setText(saved.getString("command",""));
    }
    private LanguageController controller() { ProbeService s=ProbeService.current();return s==null?null:s.language(); }
    private void submit() {
        LanguageController c=controller();if(c==null) { render();return; }
        String token=pairing.getText().toString().trim();
        if(token.matches("[a-f0-9]{48}")) getSharedPreferences("language_connection",0).edit().putString("pairing",token).apply();
        ((InputMethodManager)getSystemService(INPUT_METHOD_SERVICE)).hideSoftInputFromWindow(command.getWindowToken(),0);
        command.clearFocus();c.submit(command.getText().toString().trim(),token);render();
    }
    private void render() {
        LanguageController c=controller();boolean busy=c!=null && c.busy();execute.setEnabled(c!=null && !busy);
        command.setEnabled(!busy);stop.setEnabled(busy);exampleZh.setEnabled(!busy);exampleEn.setEnabled(!busy);setup.setEnabled(!busy);pairing.setEnabled(!busy);
        status.setText(c==null?choose("请开启 Demo Probe 无障碍服务","Enable Demo Probe accessibility service"):
            (busy || "IDLE".equals(c.phase)?"":choose("上次请求\n","Last request\n"))+LanguageText.message(c.message,english));
        summary.setText(c==null?"":LanguageText.targets(c.interpreted,english));
    }
    @Override protected void onResume() { super.onResume();LanguageController c=controller();if(c!=null)c.removeOverlay();handler.post(refresh); }
    @Override protected void onPause() { handler.removeCallbacks(refresh);LanguageController c=controller();if(c!=null && c.understanding())c.cancel();super.onPause(); }
    @Override protected void onSaveInstanceState(Bundle out) { out.putString("command",command.getText().toString());super.onSaveInstanceState(out); }
    private int id(String name) { return getResources().getIdentifier(name,"id",getPackageName()); }
    private String choose(String zh,String en) { return english?en:zh; }
    private void localize() {
        setTitle(choose("自然语言控制","Language control"));language.setText(english?"中文":"English");
        title.setText(choose("说出你想做的事","Tell me what to do"));
        scope.setText(choose("Transfer Bench · 阅读灯与风扇\n只控制实验 App，不控制真实家电。","Transfer Bench · Reading lamp & desk fan\nExperimental App only. No real appliances."));
        inputLabel.setText(choose("操作指令（支持中文和英文）","Your instruction (Chinese or English)"));
        command.setHint(choose("例如：打开阅读灯，关闭风扇","Example: Turn on the lamp and turn off the fan."));
        exampleZh.setText(choose("填入中文示例","Chinese example"));exampleEn.setText(choose("填入英文示例","English example"));
        execute.setText(choose("执行","Execute"));stop.setText(choose("停止","Stop"));
        setup.setText(choose("电脑连接设置","Connection setup"));back.setText(choose("返回教学控制台","Back to teaching"));
        pairing.setHint(choose("电脑配对码（不是 API Key）","Computer pairing code (not API key)"));
        privacy.setText(choose("此输入文字将经配对电脑发送给 GPT。模型解释可能沿用指令语言。","Your command is sent to GPT through the paired computer. Model explanations may follow the command's language."));
    }
    private TextView text(String s) { TextView v=new TextView(this);v.setText(s);v.setTextSize(16);v.setTextColor(0xff19382f);v.setPadding(0,12,0,12);v.setTextIsSelectable(true);column.addView(v);return v; }
    private Button button(String name,String label,Runnable action) { Button b=new Button(this);b.setId(id(name));b.setText(label);b.setAllCaps(false);b.setMinHeight(48);b.setOnClickListener(v->action.run());column.addView(b);return b; }
}
