package edu.sydney.probe;

/** Immutable verified data only. Every match requires CURRENT bytes and CURRENT approval. */
final class FlowReviewedBytes {
    private final String raw,hash;
    FlowReviewedBytes(String raw,String hash){
        if(raw==null||hash==null||!hash.equals(FlowDigest.sha256(raw)))
            throw new IllegalStateException("RAW_APPROVAL_MISMATCH");
        this.raw=raw;this.hash=hash;
    }
    boolean matches(String currentRaw,String currentApproval){
        // Equality with the already hashed immutable bytes implies the same SHA-256.
        // No timestamp/length/file-name cache and no approval survives revocation.
        return hash.equals(currentApproval)&&raw.equals(currentRaw);
    }
}
