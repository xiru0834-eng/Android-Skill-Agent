package edu.sydney.probe;

/** Immutable validated data, never a UI cache or approval. Live inputs are mandatory each guard. */
final class FlowReviewSnapshot {
    private final String hash,version;
    private final FlowReviewedBytes bytes;
    private static void need(boolean ok,String reason){if(!ok)throw new IllegalStateException(reason);}
    FlowReviewSnapshot(String raw,String hash,String version){
        bytes=new FlowReviewedBytes(raw,hash);
        need(version!=null&&!version.isEmpty(),"APP_VERSION");this.hash=hash;this.version=version;
    }
    void check(String currentRaw,String currentApproval,String currentVersion){
        need(version.equals(currentVersion),"APP_VERSION");
        need(hash.equals(currentApproval),"LOCAL_REVIEW_REQUIRED");
        need(bytes.matches(currentRaw,currentApproval),"RAW_APPROVAL_MISMATCH");
    }
}
