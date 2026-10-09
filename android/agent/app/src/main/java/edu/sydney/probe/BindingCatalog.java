package edu.sydney.probe;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.regex.Pattern;

/** Labels aid the human, but never establish identity or authorize input. */
public final class BindingCatalog {
    public static final class Node {
        public final String id,label;
        public final boolean usable;
        public Node(String id,String label,boolean usable) { this.id=id;this.label=label;this.usable=usable; }
        @Override public String toString() { return label+"\n"+id; }
    }
    static boolean validId(String pkg,String id) {
        return ProbePolicy.allowed(pkg) && id!=null && id.matches(Pattern.quote(pkg)+":id/[A-Za-z0-9_]{1,80}");
    }
    public static List<Node> select(String pkg,List<Node> nodes) {
        if(!ProbePolicy.allowed(pkg) || nodes==null || nodes.size()>200) throw new IllegalArgumentException("Catalog limit");
        Map<String,Integer> counts=new HashMap<>();
        for(Node node:nodes) if(node.id!=null) counts.merge(node.id,1,Integer::sum);
        List<Node> result=new ArrayList<>();
        for(Node node:nodes) if(validId(pkg,node.id) && counts.get(node.id)==1 && node.usable) result.add(node);
        return List.copyOf(result);
    }
    private BindingCatalog() {}
}
