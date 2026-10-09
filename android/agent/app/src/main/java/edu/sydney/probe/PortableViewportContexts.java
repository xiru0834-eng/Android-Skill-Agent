package edu.sydney.probe;
import java.util.function.Supplier;

/** Task-scoped context resource only: no metrics, nodes, observations or input authority. */
final class PortableViewportContexts<T> {
    private int displayId=-1;
    private T context;
    T current(int id,Supplier<T> create){
        if(id<0||create==null)throw new IllegalArgumentException("DISPLAY_UNAVAILABLE");
        if(context==null||displayId!=id){
            T next=create.get();
            if(next==null)throw new IllegalStateException("DISPLAY_UNAVAILABLE");
            context=next;displayId=id;
        }
        return context;
    }
    void clear(){context=null;displayId=-1;}
}
