package edu.sydney.probe;
/** A confirmation may be consumed once, for one unchanged preview. Not durable authority. */
final class UserCandidateGate {
    private final String snapshot;private final long created;private boolean used;
    UserCandidateGate(String snapshot,long created){this.snapshot=snapshot;this.created=created;}
    synchronized void cancel(){used=true;}
    synchronized boolean claim(String current,long now){
        if(used)return false;used=true;
        return now>=created&&now-created<120000&&snapshot.equals(current);
    }
}
