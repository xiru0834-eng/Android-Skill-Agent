package edu.sydney.probe;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.os.Bundle;
import android.widget.Button;
import android.widget.CheckBox;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import java.util.List;
import java.util.UUID;

public final class DeploymentActivity extends Activity {
    private DeploymentStore store;
    private TextView state,result;
    private LinearLayout column;
    private final CheckBox[] goals=new CheckBox[2];
    private String shown="";
    @Override public void onCreate(Bundle saved) {
        super.onCreate(saved);store=new DeploymentStore(this);
        ScrollView scroll=new ScrollView(this);column=new LinearLayout(this);column.setOrientation(1);int pad=(int)(16*getResources().getDisplayMetrics().density);column.setPadding(pad,pad,pad,pad);scroll.addView(column);setContentView(scroll);
        text("","Portable workflows",22);
        state=text("deployState","",16);
        LinearLayout top=row();button(top,"deployStop","STOP",()->{ stop();refresh(); });button(top,"deployRefresh","Refresh",this::refresh);
        for(int i=0;i<2;i++) { goals[i]=new CheckBox(this);goals[i].setId(id("deployGoal"+i));column.addView(goals[i]); }
        button(column,"deployRun","Run reviewed deployment",()-> {
            DeploymentSkill active=store.active();ProbeService service=ProbeService.current();
            if(active==null || service==null) {refresh();return;}
            service.runDeployment(active.bindingId,List.of(goals[0].isChecked(),goals[1].isChecked()));openApp(active.targetPackage);
        });
        LinearLayout draft=row();button(draft,"deployCheck","Check draft",()-> {
            DeploymentSkill s=store.draft();if(s!=null && ProbeService.current()!=null) { ProbeService.current().checkDeployment(s);openApp(s.targetPackage); }
        });button(draft,"deployReview","Review draft",this::review);
        LinearLayout files=row();button(files,"deployExport","Export",()->file("EXPORT"));button(files,"deployImport","Import draft",()->file("IMPORT"));
        button(column,"deployCreate","New workflow from reviewed demo",this::create);
        button(column,"deployRebind","Rebind active workflow",()-> { DeploymentSkill s=store.active();if(s!=null) bind(s,false);else state.setText("No reviewed workflow yet."); });
        button(column,"deployHistory","Reviewed binding history",this::history);
        result=text("deployResult","",14);refresh();
        if(saved!=null && shown.equals(saved.getString("shown"))) {goals[0].setChecked(saved.getBoolean("a"));goals[1].setChecked(saved.getBoolean("b"));}
    }
    private void create() {
        stop();String pkg=getIntent().getStringExtra("package");
        TwoStepSkill s=new TwoStepStore(this).load(pkg);
        if(s==null) {state.setText("First record and review a two-step demo for the app selected on the main screen.");return;}
        LinearLayout form=new LinearLayout(this);form.setOrientation(1);EditText[] names={new EditText(this),new EditText(this)};
        for(int i=0;i<2;i++) {names[i].setSingleLine(true);names[i].setHint("Goal "+(i+1)+" meaning (for example, lighting)");names[i].setId(id("deployName"+i));form.addView(names[i]);}
        AlertDialog dialog=new AlertDialog.Builder(this).setTitle("Name the two demonstrated goals").setView(form).setNegativeButton("Cancel",null).setPositiveButton("Continue",null).create();
        dialog.setOnShowListener(d->dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(v-> {
            try {
                DeploymentSkill base=new DeploymentSkill(UUID.randomUUID().toString(),UUID.randomUUID().toString(),"",s,
                        List.of(names[0].getText().toString().trim(),names[1].getText().toString().trim()),s.appPackage,
                        List.of(s.steps.get(0).resourceId,s.steps.get(1).resourceId));
                dialog.dismiss();bind(base,true);
            } catch(IllegalArgumentException e) {names[1].setError("Use two different, short, non-empty goal names.");}
        }));dialog.show();
    }
    private void bind(DeploymentSkill s,boolean isNew) {stop();startActivity(new Intent(this,BindingActivity.class).putExtra("base",DeploymentCodec.encode(s)).putExtra("newWorkflow",isNew));}
    private void review() {
        stop();DeploymentSkill s=store.draft();
        if(s==null || !store.canReview()) {state.setText("Read-only check the draft first, then review within 60 seconds.");return;}
        String snapshot=DeploymentCodec.encode(s);
        LinearLayout form=new LinearLayout(this);form.setOrientation(1);
        TextView details=new TextView(this);details.setText(describe(s)+"\n\nSource demonstration: "+s.source.appPackage+"\n"+s.source.steps.get(0).resourceId+"\n"+s.source.steps.get(1).resourceId+"\n\nThis app has not been demonstrated. Preflight checks control availability, not semantic equivalence. No input runs during approval.");form.addView(details);
        CheckBox confirm=new CheckBox(this);confirm.setId(id("deployConfirm"));confirm.setText("I confirm these controls represent the same two goals.");form.addView(confirm);
        int pad=(int)(16*getResources().getDisplayMetrics().density);form.setPadding(pad,0,pad,0);ScrollView content=new ScrollView(this);content.addView(form);
        AlertDialog dialog=new AlertDialog.Builder(this).setTitle("Approve new binding version?").setView(content).setNegativeButton("Cancel",null).setPositiveButton("Approve",null).create();
        dialog.setOnShowListener(d->{Button approve=dialog.getButton(AlertDialog.BUTTON_POSITIVE);approve.setEnabled(false);confirm.setOnCheckedChangeListener((b,c)->approve.setEnabled(c));approve.setOnClickListener(v->{
            try { if(confirm.isChecked() && store.review(snapshot)) {dialog.dismiss();refresh();}else details.setText("Draft changed, check expired, or history full (20). Recheck and review again."); }
            catch(IllegalArgumentException e) {details.setText("Version conflict. Existing approvals are unchanged.");}
        });});dialog.show();
    }
    private void history() {
        stop();List<DeploymentSkill> all=store.history();String[] entries=all.stream().map(s->s.targetPackage+"\n"+s.bindingId).toArray(String[]::new);
        new AlertDialog.Builder(this).setTitle("Select a locally reviewed version").setItems(entries,(d,i)->{store.activate(all.get(i).bindingId);refresh();}).setNegativeButton("Cancel",null).show();
    }
    private void file(String mode) {stop();startActivity(new Intent(this,SkillFileActivity.class).putExtra("mode",mode).putExtra("deployment",true));}
    private void openApp(String pkg) {Intent i=getPackageManager().getLaunchIntentForPackage(pkg);if(i==null) {stop();state.setText("Target app unavailable.");}else startActivity(i.addFlags(Intent.FLAG_ACTIVITY_REORDER_TO_FRONT|Intent.FLAG_ACTIVITY_SINGLE_TOP));}
    private void stop() {if(ProbeService.current()!=null)ProbeService.current().stopAll();}
    private String describe(DeploymentSkill s) {return s.targetPackage+"\n"+s.roles.get(0)+" → "+s.targetIds.get(0)+"\n"+s.roles.get(1)+" → "+s.targetIds.get(1)+"\nBinding: "+s.bindingId;}
    private void refresh() {
        DeploymentSkill s=store.active(),draft=store.draft();
        state.setText("Service "+(ProbeService.current()==null?"OFF":"ON")+" · reviewed versions: "+store.history().size()+"\n"+(s==null?"No reviewed deployment":describe(s))
                +"\nDraft: "+(draft==null?"none":draft.targetPackage+" · "+store.reason()));
        String current=s==null?"":s.bindingId;
        for(int i=0;i<2;i++) {goals[i].setEnabled(s!=null);goals[i].setText(s==null?"Goal "+(i+1):s.roles.get(i)+" — checked = ON");if(s!=null && !current.equals(shown))goals[i].setChecked(s.source.steps.get(i).defaultDesired);}
        shown=current;result.setText("Last execution (not preflight)\n"+new SkillStore(this).result());
    }
    @Override protected void onResume() {super.onResume();if(state!=null)refresh();}
    @Override protected void onSaveInstanceState(Bundle out) {out.putString("shown",shown);out.putBoolean("a",goals[0].isChecked());out.putBoolean("b",goals[1].isChecked());super.onSaveInstanceState(out);}
    private int id(String s) {return getResources().getIdentifier(s,"id",getPackageName());}
    private TextView text(String id,String label,int size) {TextView t=new TextView(this);if(!id.isEmpty())t.setId(id(id));t.setText(label);t.setTextSize(size);column.addView(t);return t;}
    private LinearLayout row() {LinearLayout r=new LinearLayout(this);column.addView(r);return r;}
    private void button(LinearLayout parent,String id,String label,Runnable action) {Button b=new Button(this);b.setId(id(id));b.setText(label);b.setOnClickListener(v->action.run());parent.addView(b);}
}
