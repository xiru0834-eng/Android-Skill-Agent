package edu.sydney.probe;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/** A bounded, text-free summary of a demonstration; never an executable skill. */
public final class DemoTrace {
    public Map<String, String> latestState() { return Map.copyOf(baseline); }
    public enum Outcome { CHANGED, UNCHANGED, UNOBSERVABLE, RAPID_UNCONFIRMED }

    public static final class Step {
        public final String targetId;
        public final long eventTime;
        public final String before;
        public final String after;
        public final Outcome outcome;

        private Step(String targetId, long eventTime, String before, String after, Outcome outcome) {
            this.targetId = targetId;
            this.eventTime = eventTime;
            this.before = before;
            this.after = after;
            this.outcome = outcome;
        }
    }

    private static final int MAX_STEPS = 30;
    private final ArrayList<Step> steps = new ArrayList<>();
    private Map<String, String> baseline = Map.of();
    private String pendingId;
    private long pendingTime;
    private String pendingBefore;
    private String lastId;
    private long lastTime = Long.MIN_VALUE;
    private int unattributedChanges;
    private int unsupportedClicks;
    private int overflowClicks;

    public List<Step> steps() { return List.copyOf(steps); }
    public int unattributedChanges() { return unattributedChanges; }
    public int unsupportedClicks() { return unsupportedClicks; }
    public int overflowClicks() { return overflowClicks; }
    public boolean hasPending() { return pendingId != null; }

    public void setBaseline(Map<String, String> state) {
        if (!hasPending()) baseline = Map.copyOf(state);
    }

    public boolean onClick(String resourceId, long eventTime) {
        if (resourceId == null || resourceId.isBlank()) {
            unsupportedClicks++;
            return false;
        }
        if (resourceId.equals(lastId) && eventTime == lastTime) return false;
        if (hasPending()) abandonPending();
        if (steps.size() >= MAX_STEPS) { overflowClicks++; return false; }
        pendingId = resourceId;
        pendingTime = eventTime;
        pendingBefore = baseline.get(resourceId);
        lastId = resourceId;
        lastTime = eventTime;
        return true;
    }

    public Step completeClick(Map<String, String> afterState) {
        if (!hasPending()) return null;
        String after = afterState.get(pendingId);
        Outcome outcome;
        if (pendingBefore == null || after == null) outcome = Outcome.UNOBSERVABLE;
        else if (pendingBefore.equals(after)) outcome = Outcome.UNCHANGED;
        else outcome = Outcome.CHANGED;
        Step step = new Step(pendingId, pendingTime, pendingBefore, after, outcome);
        steps.add(step);
        clearPending();
        baseline = Map.copyOf(afterState);
        return step;
    }

    public void abandonPending() {
        if (!hasPending()) return;
        steps.add(new Step(pendingId, pendingTime, pendingBefore, null, Outcome.RAPID_UNCONFIRMED));
        clearPending();
    }

    public void observeUnattributed(Map<String, String> state) {
        if (hasPending() || baseline.equals(state)) return;
        unattributedChanges++;
        baseline = Map.copyOf(state);
    }

    private void clearPending() {
        pendingId = null;
        pendingBefore = null;
    }
}
