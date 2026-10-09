package edu.sydney.probe;

/** Runtime-only range geometry. Never stores a demonstration coordinate or device size. */
final class RangeControl {
    enum Kind {SET_PROGRESS,BOUNDS_DRAG}
    static void require(boolean valid){if(!valid)throw new IllegalArgumentException("UNSAFE_RANGE");}
    static final class Bounds {
        final int left,top,right,bottom;
        Bounds(int l,int t,int r,int b){require(l>=0&&t>=0&&r>l&&b>t);left=l;top=t;right=r;bottom=b;}
    }
    static final class Track {
        final double leftFraction,rightFraction;final boolean reversed;
        Track(double l,double r,boolean reversed){require(Double.isFinite(l)&&Double.isFinite(r)&&0<=l&&l<r&&r<=1);leftFraction=l;rightFraction=r;this.reversed=reversed;}
    }
    static final class Plan {
        final Kind kind;final double value;final int startX,endX,y;
        Plan(Kind kind,double value,int start,int end,int y){this.kind=kind;this.value=value;startX=start;endX=end;this.y=y;}
    }
    static Plan plan(double min,double max,double current,double desired,boolean setProgress,Bounds bounds,Track reviewed){
        require(Double.isFinite(min)&&Double.isFinite(max)&&Double.isFinite(current)&&Double.isFinite(desired)&&max>min&&current>=min&&current<=max&&desired>=min&&desired<=max);
        if(setProgress)return new Plan(Kind.SET_PROGRESS,desired,0,0,0);
        require(bounds!=null&&reviewed!=null);
        double start=(current-min)/(max-min),end=(desired-min)/(max-min);
        if(reviewed.reversed){start=1-start;end=1-end;}
        double width=(double)bounds.right-bounds.left;
        int sx=(int)Math.round(bounds.left+width*(reviewed.leftFraction+start*(reviewed.rightFraction-reviewed.leftFraction)));
        int ex=(int)Math.round(bounds.left+width*(reviewed.leftFraction+end*(reviewed.rightFraction-reviewed.leftFraction)));
        // Keep endpoints inside the current node's rectangle, including 100%.
        sx=Math.min(bounds.right-1,sx);ex=Math.min(bounds.right-1,ex);
        return new Plan(Kind.BOUNDS_DRAG,desired,sx,ex,bounds.top+(bounds.bottom-bounds.top)/2);
    }
}
