package edu.sydney.probe;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.os.Bundle;
import android.widget.Button;
import android.widget.CheckBox;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import java.util.List;

/** A separate screen keeps existing single-step approval and parameter semantics intact. */
public final class TwoStepActivity extends Activity {
    private String pkg,shownSkill="";
    private TwoStepStore store;
    private TextView state,result;
    private final CheckBox[] targets=new CheckBox[2];
    private LinearLayout column;
    @Override public void onCreate(Bundle saved) {
        super.onCreate(saved);pkg=getIntent().getStringExtra("package");
        if(!ProbePolicy.allowed(pkg)) { finish();return; }
        store=new TwoStepStore(this);
        ScrollView scroll=new ScrollView(this);column=new LinearLayout(this);column.setOrientation(1);
        int p=(int)(16*getResources().getDisplayMetrics().density);column.setPadding(p,p,p,p);
        scroll.addView(column);setContentView(scroll);
        TextView title=text("","Two-step skills");title.setTextSize(22);
        text("","Teach two different switches, one at a time. Return here and STOP, then review. Both final targets must hold together.");
        state=text("twoState","");
        LinearLayout capture=row();button(capture,"twoRecord","Record",() -> { if(service()!=null) { service().startRecording(pkg);openApp(); } });
        button(capture,"twoStop","STOP",() -> { if(service()!=null) service().stopAll();refresh(); });
        LinearLayout review=row();button(review,"twoReview","Review / save",this::review);
        button(review,"twoCheck","Check bindings",() -> { TwoStepSkill s=store.draft(pkg);if(s!=null && service()!=null) { service().checkTwo(s);openApp(); } });
        for(int i=0;i<2;i++) { targets[i]=new CheckBox(this); targets[i].setId(id("twoTarget"+i));column.addView(targets[i]); }
        button(column,"twoRun","Run selected targets",() -> {
            TwoStepSkill s=store.load(pkg);
            if(s==null || service()==null) { refresh();return; }
            service().runTwo(s,List.of(targets[0].isChecked(),targets[1].isChecked()));openApp();
        });
        LinearLayout files=row();button(files,"twoExport","Export",() -> file("EXPORT"));button(files,"twoImport","Import draft",() -> file("IMPORT"));
        button(column,"twoRefresh","Refresh",this::refresh);result=text("twoResult","");
        refresh();
        if(saved!=null) { targets[0].setChecked(saved.getBoolean("a"));targets[1].setChecked(saved.getBoolean("b")); }
    }
    private ProbeService service() { return ProbeService.current(); }
    private void review() {
        TwoStepSkill s=store.draft(pkg);if(s==null) { refresh();return; }
        if(!store.canReview(pkg)) { new AlertDialog.Builder(this).setMessage("Check both imported bindings first, then review within 60 seconds.").setPositiveButton("OK",null).show();return; }
        String snapshot=TwoStepCodec.encode(s);
        StringBuilder details=new StringBuilder(store.imported(pkg)?"Source file claims:\n":"Observed changes:\n");
        for(SwitchSkill step:s.steps) details.append(step.resourceId).append('\n').append(step.demonstratedBefore).append(" → ").append(step.defaultDesired).append('\n');
        new AlertDialog.Builder(this).setTitle("Save / replace two-step skill?").setMessage(details+"\nNo actions run during review. Single-step skills are unchanged.")
                .setNegativeButton("Cancel",null).setPositiveButton("Save",(d,w) -> { if(!store.review(pkg,snapshot)) state.setText("Draft changed or check expired; review again.");else refresh(); }).show();
    }
    private void file(String mode) {
        if(service()!=null) service().stopAll();
        startActivity(new Intent(this,SkillFileActivity.class).putExtra("mode",mode).putExtra("package",pkg).putExtra("twoStep",true));
    }
    private void openApp() {
        Intent i=getPackageManager().getLaunchIntentForPackage(pkg);
        if(i==null) { if(service()!=null) service().stopAll();state.setText("App unavailable");return; }
        startActivity(i.addFlags(Intent.FLAG_ACTIVITY_REORDER_TO_FRONT|Intent.FLAG_ACTIVITY_SINGLE_TOP));
    }
    @Override protected void onResume() { super.onResume();if(state!=null) refresh(); }
    @Override protected void onSaveInstanceState(Bundle out) { out.putBoolean("a",targets[0].isChecked());out.putBoolean("b",targets[1].isChecked());super.onSaveInstanceState(out); }
    private void refresh() {
        ProbeService service=service();TwoStepSkill draft=store.draft(pkg), saved=store.load(pkg);
        String reason=draft!=null?(store.imported(pkg)?"IMPORTED: "+store.checkReason(pkg)+(store.canReview(pkg)?" · review available":" · needs check"):"READY_FOR_REVIEW")
                :service!=null && pkg.equals(service.recordingPackage())?service.twoDraftReason():"NO_DEMONSTRATION";
        state.setText(pkg+"\nService "+(service==null?"OFF":"ON")+" · recording="+(service!=null && service.isRecording())+"\nDraft: "+reason+"\nReviewed skill: "+(saved==null?"none":"saved"));
        String encoded=saved==null?"":TwoStepCodec.encode(saved);
        for(int i=0;i<2;i++) {
            targets[i].setEnabled(saved!=null);
            targets[i].setText(saved==null?"Target "+(i+1)+": no reviewed binding":(i+1)+". "+saved.steps.get(i).resourceId.split(":id/")[1]+" — checked = ON");
            if(saved!=null && !encoded.equals(shownSkill)) targets[i].setChecked(saved.steps.get(i).defaultDesired);
        }
        shownSkill=encoded;result.setText("Last run\n"+new SkillStore(this).result());
    }
    private int id(String name) { return getResources().getIdentifier(name,"id",getPackageName()); }
    private TextView text(String id,String s) { TextView t=new TextView(this);t.setText(s);t.setTextIsSelectable(true);if(!id.isEmpty())t.setId(id(id));column.addView(t);return t; }
    private LinearLayout row() { LinearLayout r=new LinearLayout(this);column.addView(r);return r; }
    private void button(LinearLayout row,String id,String label,Runnable action) { Button b=new Button(this);b.setId(id(id));b.setText(label);b.setOnClickListener(v->action.run());row.addView(b); }
}
