package edu.sydney.probe;
public final class FlowReviewSnapshotTest {
    static void bad(Runnable r,String reason){try{r.run();throw new AssertionError("accepted "+reason);}catch(IllegalStateException e){if(!reason.equals(e.getMessage()))throw e;}}
    public static void main(String[] args){
        String raw="{\"contract\":\"审核🌙\"}",hash=FlowDigest.sha256(raw);
        var snapshot=new FlowReviewSnapshot(raw,hash,"v1");snapshot.check(raw,hash,"v1");
        bad(()->snapshot.check(raw+" ",hash,"v1"),"RAW_APPROVAL_MISMATCH");
        bad(()->snapshot.check(raw,"","v1"),"LOCAL_REVIEW_REQUIRED");
        bad(()->snapshot.check(raw,"a".repeat(64),"v1"),"LOCAL_REVIEW_REQUIRED");
        bad(()->snapshot.check(raw,hash,"v2"),"APP_VERSION");
        bad(()->new FlowReviewSnapshot(raw,"a".repeat(64),"v1"),"RAW_APPROVAL_MISMATCH");
        snapshot.check(raw,hash,"v1");
        System.out.println("PASS FlowReviewSnapshotTest exact bytes/live approval/version; no enduring permission");
    }
}
