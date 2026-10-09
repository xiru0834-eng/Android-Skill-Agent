package edu.sydney.probe;

public final class ProbePolicy {
    public static final String LAB_PACKAGE = "edu.sydney.smarthomelab";
    public static final String TRANSFER_PACKAGE = "edu.sydney.transferlab";
    public static final String ROOM_PACKAGE = "edu.sydney.transferroom";

    public static boolean allowed(String pkg) {
        return LAB_PACKAGE.equals(pkg) || TRANSFER_PACKAGE.equals(pkg) || ROOM_PACKAGE.equals(pkg);
    }

    private ProbePolicy() {}

    public static boolean shouldRecord(boolean recording, String eventPackage,
                                       String foregroundPackage, boolean password, boolean editable) {
        return shouldRecord(recording, LAB_PACKAGE, eventPackage, foregroundPackage, password, editable);
    }

    public static boolean shouldRecord(boolean recording, String selectedPackage, String eventPackage,
                                       String foregroundPackage, boolean password, boolean editable) {
        return recording && allowed(selectedPackage) && selectedPackage.equals(eventPackage)
                && selectedPackage.equals(foregroundPackage) && !password && !editable;
    }
}
