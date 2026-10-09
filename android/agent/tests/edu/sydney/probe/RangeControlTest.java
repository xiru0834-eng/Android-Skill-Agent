package edu.sydney.probe;
public final class RangeControlTest {
    static int checks;
    static void ok(boolean v){checks++;if(!v)throw new AssertionError("check "+checks);}
    static void reject(Runnable r){try{r.run();throw new AssertionError("not rejected");}catch(IllegalArgumentException expected){checks++;}}
    public static void main(String[] args){
        var bounds=new RangeControl.Bounds(100,200,600,260);
        for(double v:new double[]{0,20,60,80,100})ok(RangeControl.plan(0,100,40,v,true,bounds,null).value==v);
        ok(RangeControl.plan(16,30,20,28,true,bounds,null).kind==RangeControl.Kind.SET_PROGRESS);
        reject(()->RangeControl.plan(0,100,40,101,true,bounds,null));
        reject(()->RangeControl.plan(0,100,40,Double.NaN,true,bounds,null));
        reject(()->RangeControl.plan(0,100,40,80,false,bounds,null));
        var track=new RangeControl.Track(.1,.9,false);
        var a=RangeControl.plan(0,100,40,80,false,bounds,track);
        ok(a.kind==RangeControl.Kind.BOUNDS_DRAG&&a.endX==470&&a.startX==310&&a.y==230);
        var b=RangeControl.plan(0,100,40,80,false,new RangeControl.Bounds(10,20,1010,100),track);
        ok(b.endX==750&&b.startX==430&&b.y==60);
        ok(RangeControl.plan(0,100,40,80,false,bounds,new RangeControl.Track(.1,.9,true)).endX==230);
        reject(()->new RangeControl.Track(.9,.1,false));reject(()->new RangeControl.Bounds(0,0,0,100));
        reject(()->RangeControl.plan(10,10,10,10,true,bounds,null));
        reject(()->RangeControl.plan(0,100,101,50,true,bounds,null));
        for(double invalid:new double[]{-1,Double.NEGATIVE_INFINITY,Double.POSITIVE_INFINITY})reject(()->RangeControl.plan(0,100,40,invalid,true,bounds,null));
        reject(()->RangeControl.plan(Double.NaN,100,40,80,true,bounds,null));
        reject(()->RangeControl.plan(0,Double.POSITIVE_INFINITY,40,80,true,bounds,null));
        reject(()->RangeControl.plan(0,100,Double.NaN,80,true,bounds,null));
        reject(()->RangeControl.plan(16,30,20,15,true,bounds,null));
        reject(()->RangeControl.plan(16,30,20,31,true,bounds,null));
        reject(()->new RangeControl.Bounds(-1,0,100,100));
        reject(()->new RangeControl.Track(Double.NaN,1,false));
        reject(()->new RangeControl.Track(0,Double.POSITIVE_INFINITY,false));
        ok(RangeControl.plan(0,100,0,100,false,bounds,new RangeControl.Track(0,1,false)).endX==599);
        ok(RangeControl.plan(0,100,100,0,false,bounds,new RangeControl.Track(0,1,false)).endX==100);
        ok(RangeControl.plan(0,100,40,80,true,null,null).kind==RangeControl.Kind.SET_PROGRESS);
        for(var currentBounds:new RangeControl.Bounds[]{new RangeControl.Bounds(0,0,1,1),new RangeControl.Bounds(100,200,600,260),new RangeControl.Bounds(10,20,1010,100)}){
            for(double desired:new double[]{0,20,60,80,100})for(boolean reverse:new boolean[]{false,true}){
                var plan=RangeControl.plan(0,100,40,desired,false,currentBounds,new RangeControl.Track(0,1,reverse));
                ok(plan.startX>=currentBounds.left&&plan.startX<currentBounds.right&&plan.endX>=currentBounds.left&&plan.endX<currentBounds.right&&plan.y>=currentBounds.top&&plan.y<currentBounds.bottom);
            }
        }
        System.out.println("RangeControlTest PASS "+checks+" checks");
    }
}
