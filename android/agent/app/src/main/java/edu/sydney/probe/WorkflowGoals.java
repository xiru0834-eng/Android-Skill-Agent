package edu.sydney.probe;

/** null means preserve the execution-start value, never the demonstration value. */
final class WorkflowGoals {
    static boolean valid(int version,int steps,Integer[] g){
        if(g==null||g.length!=4)return false;
        if((g[0]==null)!=(g[1]==null)||(g[2]==null)!=(g[3]==null))return false;
        int groups=(g[0]==null?0:1)+(g[2]==null?0:1);
        if(!(version==1&&steps==8&&groups==2)&&!(version==2&&steps==4&&groups==1))return false;
        for(int i=0;i<4;i++)if(g[i]!=null){int v=g[i];
            if(i==1?!(v>=20&&v<=100&&v%20==0):i==3?!(v>=1&&v<=3):!(v==0||v==1))return false;
        }return true;
    }
    static int[] bind(Integer[] requested,int[] initial){
        if(initial.length!=4||requested.length!=4)throw new IllegalArgumentException("GOAL_COUNT");
        int[] result=initial.clone();for(int i=0;i<4;i++)if(requested[i]!=null)result[i]=requested[i];return result;
    }
    static boolean preserved(Integer[] requested,int[] bound,int[] actual){
        if(requested.length!=4||bound.length!=4||actual.length!=4)return false;
        for(int i=0;i<4;i++)if(requested[i]==null&&bound[i]!=actual[i])return false;return true;
    }
}
