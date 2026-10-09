package edu.sydney.probe;
public final class PortableViewportContextsTest {
    public static void main(String[] args){
        var task=new PortableViewportContexts<Object>();int[] created={0};
        java.util.function.Supplier<Object> factory=()->{created[0]++;return new Object();};
        Object a=task.current(0,factory);
        if(task.current(0,factory)!=a||created[0]!=1)throw new AssertionError("context recreated within same task");
        if(task.current(1,factory)==a||created[0]!=2)throw new AssertionError("display context reused across display");
        task.clear();if(task.current(1,factory)==a||created[0]!=3)throw new AssertionError("scope outlived task");
        var other=new PortableViewportContexts<Object>();if(other.current(1,factory)==task.current(1,factory))throw new AssertionError("cross-task context");
        try{task.current(-1,factory);throw new AssertionError("invalid display");}catch(IllegalArgumentException expected){}
        try{task.current(2,()->null);throw new AssertionError("null resource");}catch(IllegalStateException expected){}
        System.out.println("PortableViewportContextsTest: scoped resource only; live metrics remain caller responsibility");
    }
}
