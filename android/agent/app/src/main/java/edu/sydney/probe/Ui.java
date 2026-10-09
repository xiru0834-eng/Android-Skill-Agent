package edu.sydney.probe;

import android.app.Activity;
import android.content.Context;
import android.content.res.ColorStateList;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.graphics.drawable.RippleDrawable;
import android.graphics.drawable.StateListDrawable;
import android.view.Gravity;
import android.view.View;
import android.view.WindowManager;
import android.text.SpannableString;
import android.text.Spanned;
import android.text.style.RelativeSizeSpan;
import android.text.style.StyleSpan;
import android.widget.*;

/** Small native view vocabulary. No recording, model or execution decisions. */
final class Ui {
    private Ui(){}
    static int dp(Context c,int value){return Math.round(value*c.getResources().getDisplayMetrics().density);}
    static void configure(Activity a){
        if(a.getActionBar()!=null)a.getActionBar().hide();
        a.getWindow().setStatusBarColor(UiStyle.BACKGROUND);
        a.getWindow().setNavigationBarColor(UiStyle.BACKGROUND);
        a.getWindow().getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR|View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR);
        a.getWindow().setSoftInputMode(WindowManager.LayoutParams.SOFT_INPUT_ADJUST_RESIZE);
    }
    static LinearLayout column(Context c){LinearLayout v=new LinearLayout(c);v.setOrientation(LinearLayout.VERTICAL);return v;}
    static LinearLayout page(Activity a){
        configure(a);ScrollView scroll=new ScrollView(a);scroll.setFillViewport(true);scroll.setBackgroundColor(UiStyle.BACKGROUND);
        LinearLayout frame=column(a);frame.setGravity(Gravity.CENTER_HORIZONTAL);scroll.addView(frame);
        LinearLayout body=column(a);int width=Math.min(a.getResources().getDisplayMetrics().widthPixels,dp(a,640));
        frame.addView(body,new LinearLayout.LayoutParams(width,-2));body.setPadding(dp(a,20),dp(a,12),dp(a,20),dp(a,32));a.setContentView(scroll);return body;
    }
    static TextView label(LinearLayout parent,String value,int size){
        Context c=parent.getContext();TextView v=new TextView(c);v.setText(value);v.setTextSize(size);v.setTextColor(size<16?UiStyle.MUTED:UiStyle.INK);
        v.setLineSpacing(dp(c,3),1.05f);v.setPadding(0,dp(c,4),0,dp(c,4));v.setTextIsSelectable(true);
        if(size>=18)v.setTypeface(Typeface.create("sans-serif-medium",Typeface.NORMAL));
        parent.addView(v,new LinearLayout.LayoutParams(-1,-2));return v;
    }
    static GradientDrawable surface(Context c,int colour){GradientDrawable d=new GradientDrawable();d.setColor(colour);d.setCornerRadius(dp(c,16));return d;}
    static void gap(LinearLayout parent,int height){parent.addView(new View(parent.getContext()),new LinearLayout.LayoutParams(1,dp(parent.getContext(),height)));}
    static LinearLayout panel(LinearLayout parent){
        Context c=parent.getContext();LinearLayout panel=column(c);panel.setPadding(dp(c,16),dp(c,12),dp(c,16),dp(c,16));
        GradientDrawable shape=surface(c,UiStyle.SURFACE);shape.setStroke(dp(c,1),UiStyle.BORDER);panel.setBackground(shape);
        LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(-1,-2);lp.topMargin=dp(c,12);parent.addView(panel,lp);return panel;
    }
    static void badge(TextView v){Context c=v.getContext();v.setTextSize(14);v.setBackground(surface(c,UiStyle.SOFT));v.setPadding(dp(c,12),dp(c,6),dp(c,12),dp(c,6));LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(-2,-2);lp.topMargin=dp(c,12);v.setLayoutParams(lp);}
    static void button(Button b,boolean primary){
        Context c=b.getContext();b.setAllCaps(false);b.setTextSize(16);b.setMinHeight(dp(c,48));b.setMinimumHeight(dp(c,48));b.setMinWidth(0);b.setMinimumWidth(0);
        b.setPadding(dp(c,16),dp(c,10),dp(c,16),dp(c,10));b.setGravity(Gravity.CENTER);
        b.setStateListAnimator(null);b.setElevation(0);
        GradientDrawable shape=surface(c,primary?UiStyle.ACCENT:UiStyle.SURFACE);if(!primary)shape.setStroke(dp(c,1),UiStyle.BORDER);
        StateListDrawable states=new StateListDrawable();states.addState(new int[]{-android.R.attr.state_enabled},surface(c,UiStyle.DISABLED));states.addState(new int[]{},shape);
        b.setBackgroundTintList(null);b.setBackground(new RippleDrawable(ColorStateList.valueOf(0x25235d48),states,null));
        b.setTextColor(new ColorStateList(new int[][]{new int[]{-android.R.attr.state_enabled},new int[]{}},new int[]{UiStyle.MUTED,primary?UiStyle.SURFACE:UiStyle.ACCENT}));
    }
    static Button action(LinearLayout parent,String key,String label,Runnable action,boolean primary){
        Context c=parent.getContext();Button b=new Button(c);b.setText(label);if(!key.isEmpty())b.setId(c.getResources().getIdentifier(key,"id",c.getPackageName()));
        button(b,primary);LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(-1,-2);lp.topMargin=dp(c,8);parent.addView(b,lp);b.setOnClickListener(v->action.run());return b;
    }
    static void pair(LinearLayout parent,Button first,Button second){
        pair(parent,first,second,1,1);
    }
    static void pair(LinearLayout parent,Button first,Button second,float firstWeight,float secondWeight){
        Context c=parent.getContext();parent.removeView(first);parent.removeView(second);
        int widthDp=Math.round(c.getResources().getDisplayMetrics().widthPixels/c.getResources().getDisplayMetrics().density);
        if(UiPresentation.stackActions(widthDp,c.getResources().getConfiguration().fontScale)){
            for(Button item:new Button[]{first,second}){LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(-1,-2);lp.topMargin=dp(c,8);parent.addView(item,lp);}return;
        }
        LinearLayout row=new LinearLayout(c);row.setBaselineAligned(false);row.setGravity(Gravity.CENTER_VERTICAL);
        LinearLayout.LayoutParams a=new LinearLayout.LayoutParams(0,-2,firstWeight),b=new LinearLayout.LayoutParams(0,-2,secondWeight);a.rightMargin=dp(parent.getContext(),8);
        row.addView(first,a);row.addView(second,b);LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(-1,-2);lp.topMargin=dp(parent.getContext(),8);parent.addView(row,lp);
    }
    static void quiet(Button b){
        Context c=b.getContext();b.setBackgroundTintList(null);b.setBackground(new RippleDrawable(ColorStateList.valueOf(0x25235d48),surface(c,UiStyle.BACKGROUND),null));
        b.setTextSize(14);b.setMinWidth(dp(c,48));b.setMinimumWidth(dp(c,48));b.setPadding(dp(c,8),dp(c,8),dp(c,8),dp(c,8));
    }
    static void notice(TextView v){Context c=v.getContext();v.setBackground(surface(c,UiStyle.SOFT));v.setPadding(dp(c,16),dp(c,12),dp(c,16),dp(c,12));}
    static void field(EditText v){
        Context c=v.getContext();v.setTextSize(16);v.setTextColor(UiStyle.INK);v.setHintTextColor(UiStyle.MUTED);v.setMinHeight(dp(c,52));
        GradientDrawable background=surface(c,UiStyle.SURFACE);background.setStroke(dp(c,1),UiStyle.BORDER);
        GradientDrawable focused=surface(c,UiStyle.SURFACE);focused.setStroke(dp(c,2),UiStyle.ACCENT);
        StateListDrawable states=new StateListDrawable();states.addState(new int[]{-android.R.attr.state_enabled},surface(c,UiStyle.DISABLED));states.addState(new int[]{android.R.attr.state_focused},focused);states.addState(new int[]{},background);
        v.setBackground(states);v.setPadding(dp(c,14),dp(c,12),dp(c,14),dp(c,12));
        LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(-1,-2);lp.topMargin=dp(c,4);lp.bottomMargin=dp(c,8);v.setLayoutParams(lp);
    }
    static void divider(LinearLayout parent){View v=new View(parent.getContext());v.setBackgroundColor(UiStyle.BORDER);LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(-1,dp(parent.getContext(),1));lp.topMargin=dp(parent.getContext(),16);lp.bottomMargin=dp(parent.getContext(),8);parent.addView(v,lp);}
    static void toolbar(LinearLayout parent,String title,String key,String language,Runnable toggle){
        toolbar(parent,title,key,language,toggle,"","",null);
    }
    static void toolbar(LinearLayout parent,String title,String key,String language,Runnable toggle,String backKey,String backLabel,Runnable back){
        Context c=parent.getContext();LinearLayout row=new LinearLayout(c);row.setGravity(Gravity.CENTER_VERTICAL);parent.addView(row,new LinearLayout.LayoutParams(-1,-2));
        if(back!=null){Button b=new Button(c);b.setText("‹");b.setContentDescription(backLabel);b.setId(c.getResources().getIdentifier(backKey,"id",c.getPackageName()));button(b,false);quiet(b);b.setTextSize(28);b.setOnClickListener(v->back.run());row.addView(b,new LinearLayout.LayoutParams(dp(c,48),-2));}
        TextView name=new TextView(c);name.setText(title);name.setTextColor(UiStyle.INK);name.setTextSize(20);name.setTypeface(Typeface.create("sans-serif-medium",Typeface.NORMAL));row.addView(name,new LinearLayout.LayoutParams(0,-2,1));
        Button b=new Button(c);b.setText(language);b.setId(c.getResources().getIdentifier(key,"id",c.getPackageName()));button(b,false);quiet(b);b.setBackground(new RippleDrawable(ColorStateList.valueOf(0x25235d48),surface(c,UiStyle.SOFT),null));b.setOnClickListener(v->toggle.run());LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(-2,-2);lp.leftMargin=dp(c,8);row.addView(b,lp);
    }
    static Button entry(LinearLayout parent,String key,String title,String subtitle,Runnable action,boolean primary){
        Button b=action(parent,key,title,action,primary);String text=title+"\n"+subtitle;
        SpannableString styled=new SpannableString(text);styled.setSpan(new StyleSpan(Typeface.BOLD),0,title.length(),Spanned.SPAN_EXCLUSIVE_EXCLUSIVE);
        styled.setSpan(new RelativeSizeSpan(primary?1.375f:1.125f),0,title.length(),Spanned.SPAN_EXCLUSIVE_EXCLUSIVE);
        styled.setSpan(new RelativeSizeSpan(14f/16f),title.length()+1,text.length(),Spanned.SPAN_EXCLUSIVE_EXCLUSIVE);
        b.setText(styled);b.setGravity(Gravity.START|Gravity.CENTER_VERTICAL);b.setMinHeight(dp(parent.getContext(),primary?108:88));b.setLineSpacing(dp(parent.getContext(),8),1.05f);b.setPadding(dp(parent.getContext(),20),dp(parent.getContext(),18),dp(parent.getContext(),20),dp(parent.getContext(),18));return b;
    }
    static TextView[] stages(LinearLayout parent,boolean en){
        Context c=parent.getContext();LinearLayout row=new LinearLayout(c);row.setGravity(Gravity.CENTER_VERTICAL);
        LinearLayout.LayoutParams rp=new LinearLayout.LayoutParams(-1,-2);rp.topMargin=dp(c,8);rp.bottomMargin=dp(c,12);parent.addView(row,rp);
        String[] labels=en?new String[]{"1  Record","2  Review","3  Save"}:new String[]{"1  录制","2  核对","3  保存"};TextView[] result=new TextView[3];
        for(int i=0;i<3;i++){TextView v=new TextView(c);v.setText(labels[i]);v.setTextSize(14);v.setGravity(Gravity.CENTER);v.setPadding(dp(c,4),dp(c,8),dp(c,4),dp(c,8));LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(0,-2,1);if(i>0)lp.leftMargin=dp(c,4);row.addView(v,lp);result[i]=v;}return result;
    }
    static void stage(TextView[] views,String kind,boolean en){
        int active=UiPresentation.stage(kind);for(int i=0;i<views.length;i++){TextView v=views[i];if(Integer.valueOf(active).equals(v.getTag()))continue;v.setTag(active);v.setBackground(surface(v.getContext(),i==active?UiStyle.ACCENT:UiStyle.BACKGROUND));v.setTextColor(i==active?UiStyle.SURFACE:UiStyle.MUTED);v.setContentDescription(v.getText()+(i==active?(en?", current stage":"，当前阶段"):(en?", workflow stage":"，流程阶段")));}
    }
}
