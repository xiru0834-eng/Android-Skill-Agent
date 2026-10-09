package edu.sydney.probe;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.os.Bundle;
import android.text.InputFilter;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.RadioButton;
import android.widget.RadioGroup;
import android.widget.ScrollView;
import android.widget.TextView;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;

/** Local-only evidence workbench. Recovery creates an unapproved, check-required v2 draft. */
public final class TraceActivity extends Activity {
    private String pkg,pendingExport;
    private boolean preserveExportNotice;
    private TraceStore store;
    private LinearLayout column;
    private EditText goal;
    private RadioGroup sources;
    private TextView status,preview;
    @Override public void onCreate(Bundle state) {
        super.onCreate(state);pkg=getIntent().getStringExtra("package");
        if(!ProbePolicy.allowed(pkg)) { finish();return; }
        store=new TraceStore(this);ScrollView scroll=new ScrollView(this);
        column=new LinearLayout(this);column.setOrientation(1);int p=(int)(16*getResources().getDisplayMetrics().density);
        column.setPadding(p,p,p,p);scroll.addView(column);setContentView(scroll);
        text("","Local demonstration evidence").setTextSize(22);
        text("","State evidence only; no screenshots, cloud requests or model learning. Source is your declaration, not automatic detection.");
        text("","New recording · task goal (non-sensitive, English)");
        goal=new EditText(this);goal.setId(id("traceGoal"));goal.setSingleLine(true);goal.setHint("For example: turn both switches on");
        goal.setContentDescription("Task goal");goal.setFilters(new InputFilter[]{new InputFilter.LengthFilter(240)});column.addView(goal);
        sources=new RadioGroup(this);column.addView(sources);
        source("traceUnknown","Unknown source");source("traceHuman","Human demonstration (declared)");source("traceAdb","ADB automated test");
        sources.check(id("traceUnknown"));
        LinearLayout capture=new LinearLayout(this);column.addView(capture);
        button(capture,"traceRecord","Record locally",this::record);
        button(capture,"traceStop","Stop / save",() -> { if(service()!=null) service().stopAll();refresh(); });
        status=text("traceStatus","");
        button(column,"traceRefresh","Refresh evidence",this::refresh);
        button(column,"traceRestore","Create rule draft for review",this::restore);
        button(column,"traceExport","Export evidence (not a skill)",this::export);
        button(column,"traceDelete","Delete latest evidence",this::delete);
        text("","Saved evidence (independent of the form above)").setTextSize(18);
        preview=text("tracePreview","");
        if(state!=null) pendingExport=state.getString("pendingExport");
        refresh();
    }
    private ProbeService service() { return ProbeService.current(); }
    private void record() {
        if(service()==null) { status.setText("Accessibility service is OFF. Enable it in system settings first.");return; }
        String purpose=goal.getText().toString().trim();
        if(purpose.isEmpty()) { goal.setError("Describe what you intend to teach");return; }
        TraceBundle.Source source=sources.getCheckedRadioButtonId()==id("traceHuman")?TraceBundle.Source.HUMAN_DECLARED
                :sources.getCheckedRadioButtonId()==id("traceAdb")?TraceBundle.Source.ADB_TEST:TraceBundle.Source.UNKNOWN;
        new AlertDialog.Builder(this).setTitle("Start local recording?")
                .setMessage("Only "+pkg+" is recorded. This replaces its latest evidence; export it first if needed. Existing approved skills are kept. No data is uploaded.")
                .setNegativeButton("Cancel",null).setPositiveButton("Record",(d,w) -> {
                    Intent launch=getPackageManager().getLaunchIntentForPackage(pkg);
                    if(launch==null || service()==null) { status.setText("App or service unavailable");return; }
                    try { service().startRecording(pkg,purpose,source);startActivity(launch.addFlags(Intent.FLAG_ACTIVITY_REORDER_TO_FRONT|Intent.FLAG_ACTIVITY_SINGLE_TOP)); }
                    catch(RuntimeException error) { status.setText("Recording could not start. Check task metadata and app availability."); }
                }).show();
    }
    private TraceBundle stoppedEvidence() {
        if(service()!=null && service().isRecording()) throw new IllegalArgumentException("Stop recording first");
        TraceBundle b=store.load(pkg);if(b==null) throw new IllegalArgumentException("No saved evidence");return b;
    }
    private void restore() {
        try {
            TraceBundle b=stoppedEvidence();TwoStepSkill candidate=b.candidate();
            if(candidate==null) { status.setText("Cannot create draft: "+b.candidateReason());return; }
            String expected=TraceCodec.encode(b);
            new AlertDialog.Builder(this).setTitle("Create an unapproved rule draft?")
                    .setMessage("Two observed boolean changes only. This does not check that the goal's language matches the actions. Check both bindings, then review in Two-step skills. Existing approved skills remain unchanged.")
                    .setNegativeButton("Cancel",null).setPositiveButton("Create draft",(d,w) -> {
                        try {
                            if(!expected.equals(TraceCodec.encode(stoppedEvidence()))) throw new IllegalArgumentException("Evidence changed");
                            if(!new TwoStepStore(this).setDraft(pkg,candidate,true)) throw new IllegalArgumentException("Save failed");
                            startActivity(new Intent(this,TwoStepActivity.class).putExtra("package",pkg));
                        } catch(RuntimeException error) { status.setText("Evidence changed or draft could not be saved. Refresh and review again."); }
                    }).show();
        } catch(RuntimeException error) { status.setText("No usable stopped evidence. Stop recording and refresh; corrupt records cannot be recovered."); }
    }
    private void export() {
        try {
            pendingExport=TraceCodec.encode(stoppedEvidence());
            Intent intent=new Intent(Intent.ACTION_CREATE_DOCUMENT).addCategory(Intent.CATEGORY_OPENABLE).setType("application/json")
                    .putExtra(Intent.EXTRA_TITLE,"trace-"+pkg+".json");startActivityForResult(intent,71);
        } catch(RuntimeException error) { status.setText("Stop recording and load valid evidence before exporting."); }
    }
    private void delete() {
        try {
            TraceBundle b=stoppedEvidence();
            new AlertDialog.Builder(this).setTitle("Delete this local evidence?")
                    .setMessage("Deletes only the latest evidence for this app. Exported copies and independently approved skills are not deleted or revoked.")
                    .setNegativeButton("Cancel",null).setPositiveButton("Delete",(d,w) -> {
                        try {
                            if(service()!=null && service().isRecording()) throw new IllegalArgumentException("Recording");
                            if(!store.remove(pkg,b.traceId)) throw new IllegalArgumentException("Evidence changed");refresh();
                        } catch(RuntimeException error) { status.setText("Evidence changed or delete failed; nothing else was removed."); }
                    }).show();
        } catch(RuntimeException error) { status.setText("Stop recording and load valid evidence first."); }
    }
    @Override protected void onActivityResult(int request,int result,Intent data) {
        super.onActivityResult(request,result,data);
        if(request!=71) return;
        preserveExportNotice=true;
        String json=pendingExport;pendingExport=null;
        if(result!=RESULT_OK) { status.setText("Export cancelled. Local evidence retained.");return; }
        try {
            if(json==null || data==null || data.getData()==null) throw new IllegalArgumentException("Export state lost");
            try(OutputStream stream=getContentResolver().openOutputStream(data.getData(),"wt")) {
                if(stream==null) throw new IllegalArgumentException("No provider");stream.write(json.getBytes(StandardCharsets.UTF_8));
            }
            status.setText("Evidence exported. It contains no approval and is not a runnable skill.");
        } catch(Exception error) { status.setText("Export failed; local evidence retained. The selected output file may be incomplete."); }
    }
    @Override protected void onResume() {
        super.onResume();
        if(preserveExportNotice) preserveExportNotice=false;
        else if(status!=null) refresh();
    }
    @Override protected void onSaveInstanceState(Bundle out) { out.putString("pendingExport",pendingExport);super.onSaveInstanceState(out); }
    private void refresh() {
        boolean recording=service()!=null && service().isRecording();
        try {
            TraceBundle b=store.load(pkg);
            status.setText("Selected: "+pkg+"\nService "+(service()==null?"OFF":"ON")+" · recording="+recording
                    +(service()==null?"":"\n"+service().traceStorage()));
            if(b==null) { preview.setText("No saved evidence. Enter a task goal to begin.");return; }
            StringBuilder body=new StringBuilder("Trace: ").append(b.traceId).append("\nGoal: ").append(b.goal)
                    .append("\nSource: ").append(b.source).append(" (declared)").append("\nApp version: ").append(b.appVersion)
                    .append("\nEnd: ").append(b.end).append(b.end==TraceBundle.End.RECORDING && !recording?" — interrupted / not stopped":"")
                    .append("\nRule candidate: ").append(b.candidateReason()).append("\nScope: target states only; no images; no model\n")
                    .append("Unmatched / unsupported / overflow: ").append(b.unattributedChanges).append(" / ").append(b.unsupportedClicks).append(" / ").append(b.overflowClicks).append('\n');
            int n=0;for(TraceBundle.Step step:b.steps) body.append('\n').append(++n).append(". ").append(step.targetId).append('\n')
                    .append(step.before).append(" → ").append(step.after).append(" · ").append(step.outcome).append('\n');
            preview.setText(body);
        } catch(RuntimeException error) { status.setText("Stored evidence is invalid. No candidate is available.");preview.setText("Old skills are unchanged. Exported evidence is independent from skill approvals."); }
    }
    private int id(String name) { return getResources().getIdentifier(name,"id",getPackageName()); }
    private TextView text(String name,String value) { TextView t=new TextView(this);if(!name.isEmpty())t.setId(id(name));t.setText(value);t.setTextIsSelectable(true);column.addView(t);return t; }
    private void source(String name,String value) { RadioButton r=new RadioButton(this);r.setId(id(name));r.setText(value);sources.addView(r); }
    private void button(LinearLayout parent,String name,String label,Runnable action) { Button b=new Button(this);b.setId(id(name));b.setText(label);b.setOnClickListener(v->action.run());parent.addView(b); }
}
