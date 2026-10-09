package edu.sydney.probe;

/** Immutable data reuse must never reuse approval or accept merely similar bytes. */
public final class FlowReviewedBytesTest {
    static void need(boolean ok){if(!ok)throw new AssertionError("reviewed bytes");}
    public static void main(String[] args){
        String raw="{\"value\":\"审核🌙\"}",hash=FlowDigest.sha256(raw);
        var reviewed=new FlowReviewedBytes(raw,hash);
        need(reviewed.matches(new String(raw),hash));
        need(!reviewed.matches(raw+" ",hash));
        need(!reviewed.matches(raw,"a".repeat(64)));
        need(!reviewed.matches(null,hash));need(!reviewed.matches(raw,null));
        need(!reviewed.matches(raw.replace("审核","審核"),hash));
        String changed=raw.replace("value","other");
        need(!reviewed.matches(changed,FlowDigest.sha256(changed)));
        try{new FlowReviewedBytes(raw,"a".repeat(64));throw new AssertionError("unverified snapshot");}
        catch(IllegalStateException expected){need(expected.getMessage().equals("RAW_APPROVAL_MISMATCH"));}
        // Approval revocation and restoration remain live on every check.
        need(!reviewed.matches(raw,""));need(reviewed.matches(raw,hash));
        System.out.println("PASS FlowReviewedBytesTest exact bytes, live approval, Unicode, null, tamper");
    }
}
