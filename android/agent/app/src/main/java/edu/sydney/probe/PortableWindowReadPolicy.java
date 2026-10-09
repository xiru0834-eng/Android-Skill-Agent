package edu.sydney.probe;
/** Visible system windows without any application window cannot authorize app input. */
final class PortableWindowReadPolicy {
    static String failure(boolean rootReadable,int windowCount,int applicationWindows){
        if(rootReadable)return "";
        return windowCount>0&&applicationWindows==0?"STALE_WINDOWS":"NO_TREE";
    }
    static String failure(boolean rootReadable,int windowCount,int applicationWindows,boolean foregroundApplication){
        if(!rootReadable&&applicationWindows>0&&!foregroundApplication)return "STALE_WINDOWS";
        return failure(rootReadable,windowCount,applicationWindows);
    }
    static boolean foreign(int known,boolean knownPresent,int applications,boolean foreignForeground){
        return known>=0&&applications>0&&(!knownPresent||foreignForeground);
    }
    /** Cached target-window IDs are diagnostic only; current Root and post-read windows decide. */
    static String preRootFailure(int windowCount,int applications,boolean ime){
        if(ime)return "BLOCKED_BY_OVERLAY";
        return windowCount>0&&applications==0?"STALE_WINDOWS":"";
    }
    /** A missing root identity proves inconsistency, not which App owns the new window. */
    static String postRootFailure(boolean rootPresent,int applications,boolean foreignForeground,boolean ime){
        if(ime)return "BLOCKED_BY_OVERLAY";
        if(applications<0)return "ROOT_READ_FAILED";
        if(!rootPresent||applications==0)return "STALE_WINDOWS";
        return foreignForeground?"BLOCKED_BY_OVERLAY":"";
    }
}
