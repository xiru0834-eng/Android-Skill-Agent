package edu.sydney.probe;

public final class ProbePolicyTest {
    public static void main(String[] args) {
        assertFalse(ProbePolicy.shouldRecord(false, ProbePolicy.LAB_PACKAGE, ProbePolicy.LAB_PACKAGE, false, false));
        assertFalse(ProbePolicy.shouldRecord(true, "other.app", ProbePolicy.LAB_PACKAGE, false, false));
        assertFalse(ProbePolicy.shouldRecord(true, ProbePolicy.LAB_PACKAGE, "other.app", false, false));
        assertFalse(ProbePolicy.shouldRecord(true, ProbePolicy.LAB_PACKAGE, ProbePolicy.LAB_PACKAGE, true, false));
        assertFalse(ProbePolicy.shouldRecord(true, ProbePolicy.LAB_PACKAGE, ProbePolicy.LAB_PACKAGE, false, true));
        assertTrue(ProbePolicy.shouldRecord(true, ProbePolicy.LAB_PACKAGE, ProbePolicy.LAB_PACKAGE, false, false));
        assertTrue(ProbePolicy.shouldRecord(true, ProbePolicy.TRANSFER_PACKAGE, ProbePolicy.TRANSFER_PACKAGE, ProbePolicy.TRANSFER_PACKAGE, false, false));
        assertFalse(ProbePolicy.shouldRecord(true, ProbePolicy.LAB_PACKAGE, ProbePolicy.TRANSFER_PACKAGE, ProbePolicy.TRANSFER_PACKAGE, false, false));
        System.out.println("ProbePolicyTest passed");
    }

    private static void assertTrue(boolean value) {
        if (!value) throw new AssertionError("expected true");
    }

    private static void assertFalse(boolean value) {
        if (value) throw new AssertionError("expected false");
    }
}
