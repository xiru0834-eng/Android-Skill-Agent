package edu.sydney.probe;

/** Start the one owned worker without waiting behind Activity lifecycle/render messages. */
final class PortableWorker {
    static Thread start(Runnable work){
        Thread thread=new Thread(java.util.Objects.requireNonNull(work),"portable-skill-runtime");
        thread.start();return thread;
    }
}
