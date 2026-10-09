package edu.sydney.probe;
import java.util.*;

/** Ordered lab primitives, independent of Android, JSON and task length. */
final class FlexibleWorkflow {
    static final int[][] OPTIONS={{0,1},{20,40,60,80,100},{0,1},{1,2,3}};
    static void need(boolean ok,String code){if(!ok)throw new IllegalArgumentException(code);}
    static boolean valid(Integer[] values,boolean partial){
        if(values==null||values.length!=4)return false;
        for(int i=0;i<4;i++){
            if(values[i]==null){if(!partial)return false;continue;}
            boolean found=false;for(int v:OPTIONS[i])if(v==values[i])found=true;if(!found)return false;
        }return true;
    }
    // Resource budget grows with the demonstrated process, never resets per step.
    static long budgetMs(int steps){return WorkflowResources.defaults().runMs(steps);}
    /** Ambiguous labels are accepted only when exactly one full observed transition fits. */
    static String resolve(State before,List<String> ids,String page,Map<String,Boolean> values,int[] saved,boolean dirty){
        if(ids==null||ids.size()<2||ids.size()>16||new HashSet<>(ids).size()!=ids.size())return "";
        String found="";
        for(String id:ids){
            try{
                Boolean desired=(id.contains("Power")||id.contains("Value"))?values.get(id):null;
                action(id,before.page,desired);
                State candidate=before.copy();
                if(id.endsWith("Power")&&Objects.equals(desired,before.values().get(id)))continue;
                candidate.apply(id,desired);
                boolean match=candidate.page.equals(page)&&candidate.values().equals(values)&&candidate.dirty()==dirty
                    &&Arrays.equals(saved,List.of("overview","single").contains(page)?candidate.saved:new int[0]);
                if(match){if(!found.isEmpty())return "";found=id;}
            }catch(Exception e){return "";}
        }return found;
    }
    static final class Action {
        final String operation,afterPage;final int field;final Integer value;
        final Integer[] commitGoals=new Integer[4];
        Action(String op,String page,int field,Integer value){operation=op;afterPage=page;this.field=field;this.value=value;}
    }
    static Action action(String id,String page,Boolean desired){
        need(id!=null,"ACTION_ID");
        switch(id){
            case "wfSingle":need(page.equals("overview")&&desired==null,"ROUTE");return new Action("NAVIGATE","single",-1,null);
            case "wfMulti":need(page.equals("single")&&desired==null,"ROUTE");return new Action("NAVIGATE","overview",-1,null);
            case "wfOpenLamp":case "wfOpenFan":
                need(page.equals("overview")&&desired==null,"ROUTE");return new Action("NAVIGATE",id.equals("wfOpenLamp")?"lamp":"fan",-1,null);
        }
        for(int i:new int[]{0,2}){
            String group=i==0?"Lamp":"Fan",prefix="wf"+group;
            if(!id.startsWith(prefix))continue;
            need(page.equals("single")||page.equals(group.toLowerCase(Locale.ROOT)),"WRONG_PAGE");
            String tail=id.substring(prefix.length());
            if(tail.equals("Power")){need(desired!=null,"DESIRED");return new Action("SET",page,i,desired?1:0);}
            for(int v:OPTIONS[i+1])if(tail.equals("Value"+v)){need(Boolean.TRUE.equals(desired),"DESIRED");return new Action("SET",page,i+1,v);}
            need(desired==null,"DESIRED");
            if(tail.equals("Save")||tail.equals("Cancel"))return new Action(tail.toUpperCase(Locale.ROOT),page.equals("single")?"single":"overview",i,null);
            if(tail.equals("Back")){need(!page.equals("single"),"ROUTE");return new Action("NAVIGATE","overview",i,null);}
        }
        throw new IllegalArgumentException("UNSUPPORTED_ACTION");
    }
    static final class State {
        private String page;
        private final int[] saved,draft;
        private final Integer[] pending=new Integer[4],goals=new Integer[4];
        State(String page,int[] initial){
            need(List.of("overview","single").contains(page),"START_PAGE");
            need(initial!=null&&initial.length==4,"GOAL_COUNT");
            Integer[] v=new Integer[4];for(int i=0;i<4;i++)v[i]=initial[i];need(valid(v,false),"GOAL_VALUE");
            this.page=page;saved=initial.clone();draft=initial.clone();
        }
        private State(State other){page=other.page;saved=other.saved.clone();draft=other.draft.clone();
            System.arraycopy(other.pending,0,pending,0,4);System.arraycopy(other.goals,0,goals,0,4);}
        State copy(){return new State(this);}
        String page(){return page;}
        int[] saved(){return saved.clone();}
        Integer[] goals(){return goals.clone();}
        boolean dirty(){
            int first=page.equals("fan")?2:0,end=page.equals("lamp")?2:4;
            for(int i=first;i<end;i++)if(saved[i]!=draft[i])return true;return false;
        }
        Map<String,Boolean> values(){
            Map<String,Boolean> values=new HashMap<>();
            for(int i:new int[]{0,2}){
                String group=i==0?"Lamp":"Fan";
                if(!page.equals("single")&&!page.equals(group.toLowerCase(Locale.ROOT)))continue;
                values.put("wf"+group+"Power",draft[i]==1);
                for(int v:OPTIONS[i+1])values.put("wf"+group+"Value"+v,draft[i+1]==v);
            }return values;
        }
        Action apply(String id,Boolean desired){
            Action a=action(id,page,desired);int i=a.field;
            switch(a.operation){
                case "SET":draft[i]=a.value;pending[i]=a.value;break;
                case "SAVE":
                    for(int f=i;f<i+2;f++){saved[f]=draft[f];a.commitGoals[f]=pending[f];if(pending[f]!=null)goals[f]=pending[f];pending[f]=null;}break;
                case "CANCEL":for(int f=i;f<i+2;f++){draft[f]=saved[f];pending[f]=null;}break;
                default:
                    for(int f=i<0?0:i;f<(i<0?4:i+2);f++)need(saved[f]==draft[f],"UNSAVED_NAVIGATION");
            }
            page=a.afterPage;return a;
        }
        boolean complete(){return List.of("overview","single").contains(page)&&Arrays.equals(saved,draft)&&Arrays.stream(goals).anyMatch(Objects::nonNull);}
    }
}
