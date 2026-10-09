package edu.sydney.probe;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public final class PortableWorkerTest {
    public static void main(String[] args)throws Exception{
        Thread caller=Thread.currentThread();CountDownLatch ran=new CountDownLatch(1);
        AtomicInteger calls=new AtomicInteger();
        Thread worker=PortableWorker.start(()->{
            if(Thread.currentThread()==caller)throw new AssertionError("caller thread");
            calls.incrementAndGet();ran.countDown();
        });
        // The caller remains blocked. Dispatch must not depend on its event queue.
        if(!ran.await(2,TimeUnit.SECONDS))throw new AssertionError("queued behind caller");
        worker.join(2000);
        if(worker.isAlive()||calls.get()!=1||!worker.getName().equals("portable-skill-runtime"))throw new AssertionError("worker lifecycle");
        System.out.println("PASS PortableWorkerTest asynchronous once; no caller/UI queue dependency");
    }
}
