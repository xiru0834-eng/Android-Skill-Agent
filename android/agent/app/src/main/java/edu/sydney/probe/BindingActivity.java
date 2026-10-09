package edu.sydney.probe;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.os.Bundle;
import android.os.SystemClock;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import java.util.List;
import java.util.UUID;

/** Explicit human mapping, never an automatic claim of cross-app semantic equivalence. */
public final class BindingActivity extends Activity {
    private DeploymentSkill base;
    private String pkg;
    private final String[] selected=new String[2];
    private long catalogAt=-1;
    private TextView status;
    private final Button[] picks=new Button[2];
    private LinearLayout column;
    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        try { base=DeploymentCodec.decode(getIntent().getStringExtra("base")); } catch(IllegalArgumentException e) { finish();return; }
        pkg=state==null?ProbePolicy.ROOM_PACKAGE:state.getString("pkg",ProbePolicy.ROOM_PACKAGE);
        if(!ProbePolicy.allowed(pkg)) { finish();return; }
        ScrollView scroll=new ScrollView(this);column=new LinearLayout(this);column.setOrientation(1);int pad=(int)(16*getResources().getDisplayMetrics().density);column.setPadding(pad,pad,pad,pad);scroll.addView(column);setContentView(scroll);
        label("Map the same goals to a target app",22);
        label("Read-only scan; select a control for each goal. No target demonstration is implied. Review is required after saving this draft.",16);
        status=label("",16);status.setId(getResources().getIdentifier("bindStatus","id",getPackageName()));
        button("bindRoom","Room Controls",()->chooseApp(ProbePolicy.ROOM_PACKAGE));
        button("bindBench","Transfer Bench",()->chooseApp(ProbePolicy.TRANSFER_PACKAGE));
        button("bindScan","Scan current controls",()-> {
            ProbeService s=ProbeService.current();if(s==null) {status.setText("Enable Demo Probe service first.");return;}
            catalogAt=-1;selected[0]=selected[1]=null;s.scanDeployment(pkg);openApp();
        });
        for(int i=0;i<2;i++) { final int slot=i;picks[i]=button("bindPick"+i,"",()->pick(slot)); }
        button("bindSave","Save mapping draft",this::save);
        button("bindRefresh","Refresh scan",this::refresh);
        if(state!=null) { catalogAt=state.getLong("at",-1);selected[0]=state.getString("a");selected[1]=state.getString("b"); }
        refresh();
    }
    private void chooseApp(String value) { if(ProbeService.current()!=null) ProbeService.current().stopAll();pkg=value;catalogAt=-1;selected[0]=selected[1]=null;refresh(); }
    private DeploymentController.Catalog catalog() {
        ProbeService s=ProbeService.current();DeploymentController.Catalog c=s==null?null:s.deployments().catalog();
        long now=SystemClock.elapsedRealtime();
        return c!=null && c.pkg.equals(pkg) && c.reason.equals("READY") && now>=c.capturedAt && now-c.capturedAt<=60000?c:null;
    }
    private void pick(int slot) {
        DeploymentController.Catalog c=catalog();if(c==null) { refresh();return; }
        if(catalogAt!=c.capturedAt) { selected[0]=selected[1]=null;catalogAt=c.capturedAt; }
        String[] labels=c.nodes.stream().map(Object::toString).toArray(String[]::new);
        new AlertDialog.Builder(this).setTitle(base.roles.get(slot)).setItems(labels,(d,index)-> {
            if(catalog()!=c) { refresh();return; }selected[slot]=c.nodes.get(index).id;refresh();
        }).setNegativeButton("Cancel",null).show();
    }
    private void save() {
        DeploymentController.Catalog c=catalog();
        if(c==null || c.capturedAt!=catalogAt || selected[0]==null || selected[1]==null) { status.setText("Scan and select both targets first.");return; }
        for(String id:selected) if(c.nodes.stream().noneMatch(n->n.id.equals(id))) {status.setText("Selection is not in the current scan.");return;}
        try {
            DeploymentSkill next=new DeploymentSkill(base.workflowId,UUID.randomUUID().toString(),getIntent().getBooleanExtra("newWorkflow",false)?"":base.bindingId,
                    base.source,base.roles,pkg,List.of(selected[0],selected[1]));
            if(new DeploymentStore(this).importDraft(DeploymentCodec.encode(next))) finish();else status.setText("Draft could not be saved.");
        } catch(IllegalArgumentException e) { status.setText("Mapping rejected: select two different, valid controls. Existing approvals are unchanged."); }
    }
    private void openApp() {
        Intent i=getPackageManager().getLaunchIntentForPackage(pkg);
        if(i==null) { ProbeService.current().stopAll();status.setText("Install the selected test app first.");return; }
        startActivity(i.addFlags(Intent.FLAG_ACTIVITY_REORDER_TO_FRONT|Intent.FLAG_ACTIVITY_SINGLE_TOP));
    }
    private void refresh() {
        DeploymentController.Catalog c=catalog();
        status.setText("Target: "+pkg+"\nScan: "+(c==null?"not ready / expired — scan then return here":c.nodes.size()+" unique usable controls; inputs=0"));
        for(int i=0;i<2;i++) { picks[i].setText(base.roles.get(i)+" → "+(selected[i]==null?"Select control":selected[i].split(":id/")[1]));picks[i].setEnabled(c!=null); }
    }
    @Override protected void onResume() {super.onResume();if(status!=null)refresh();}
    @Override protected void onSaveInstanceState(Bundle out) { out.putString("pkg",pkg);out.putLong("at",catalogAt);out.putString("a",selected[0]);out.putString("b",selected[1]);super.onSaveInstanceState(out); }
    private TextView label(String text,int size) {TextView v=new TextView(this);v.setText(text);v.setTextSize(size);column.addView(v);return v;}
    private Button button(String id,String title,Runnable action) {Button b=new Button(this);b.setId(getResources().getIdentifier(id,"id",getPackageName()));b.setText(title);b.setOnClickListener(v->action.run());column.addView(b);return b;}
}
