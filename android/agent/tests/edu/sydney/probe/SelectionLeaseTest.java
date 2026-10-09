package edu.sydney.probe;

public final class SelectionLeaseTest {
    public static void main(String[] args){
        SelectionLease lease=new SelectionLease(100L,9000);
        if(lease.remainingMillis(100L)!=9000)throw new AssertionError("budget");
        if(lease.remainingMillis(1_000_000_100L)!=8000)throw new AssertionError("shared remainder");
        lease.cancel();lease.cancel();
        expect("SELECTION_CANCELLED",()->lease.remainingMillis(100L));
        SelectionLease late=new SelectionLease(0L,9000);
        expect("SELECTION_DEADLINE",()->late.remainingMillis(9_000_000_000L));
        expect("SELECTION_DEADLINE",()->late.remainingMillis(10_000_000_000L));
        if(new SelectionLease(0L,9000).remainingMillis(8_999_999_999L)!=1)throw new AssertionError("positive remainder rounds up");
        SelectionLease other=new SelectionLease(0L,9000);
        if(other.remainingMillis(0L)!=9000)throw new AssertionError("isolated request");
        expect("INVALID_BUDGET",()->new SelectionLease(0L,0));
        System.out.println("PASS SelectionLeaseTest: deadline, cancellation, isolation, remaining time");
    }
    private static void expect(String code,Runnable run){
        try{run.run();throw new AssertionError("expected "+code);}catch(IllegalArgumentException e){if(!code.equals(e.getMessage()))throw new AssertionError(e);}
    }
}
