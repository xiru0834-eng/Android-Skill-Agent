package edu.sydney.probe;

import org.json.JSONObject;
import android.util.JsonReader;
import android.util.JsonToken;
import java.io.StringReader;
import java.util.HashMap;
import java.util.Map;
import java.util.Set;

/** Validates stored data independently of the demonstration compiler. */
public final class SkillCodec {
    private SkillCodec() {}
    public static String encode(SwitchSkill skill) {
        try {
            return new JSONObject().put("schemaVersion", 1)
                    .put("workflow", new JSONObject().put("operation", "SET_CHECKED")
                            .put("parameter", "desired").put("valueType", "boolean"))
                    .put("binding", new JSONObject().put("appPackage", skill.appPackage)
                            .put("resourceId", skill.resourceId))
                    .put("evidence", new JSONObject().put("before", skill.demonstratedBefore)
                            .put("after", skill.defaultDesired)).toString();
        } catch (Exception e) { throw new IllegalArgumentException("Cannot encode skill", e); }
    }
    public static SwitchSkill decode(String json) {
        try {
            if (json == null || json.length() > 8192) throw new IllegalArgumentException("Size");
            JsonReader reader = new JsonReader(new StringReader(json));
            reader.setLenient(false);
            Map<String, Object> root = object(reader, 1);
            if (reader.peek() != JsonToken.END_DOCUMENT) throw new IllegalArgumentException("Trailing content");
            reader.close();
            keys(root, Set.of("schemaVersion", "workflow", "binding", "evidence"));
            if (!Integer.valueOf(1).equals(root.get("schemaVersion")))
                throw new IllegalArgumentException("Version");
            Map<String, Object> workflow = child(root, "workflow");
            keys(workflow, Set.of("operation", "parameter", "valueType"));
            if (!"SET_CHECKED".equals(workflow.get("operation")) || !"desired".equals(workflow.get("parameter"))
                    || !"boolean".equals(workflow.get("valueType"))) throw new IllegalArgumentException("Workflow");
            Map<String, Object> binding = child(root, "binding"), evidence = child(root, "evidence");
            keys(binding, Set.of("appPackage", "resourceId")); keys(evidence, Set.of("before", "after"));
            if (!(binding.get("appPackage") instanceof String) || !(binding.get("resourceId") instanceof String)
                    || !(evidence.get("before") instanceof Boolean) || !(evidence.get("after") instanceof Boolean))
                throw new IllegalArgumentException("Types");
            return new SwitchSkill((String)binding.get("appPackage"), (String)binding.get("resourceId"),
                    (Boolean)evidence.get("before"), (Boolean)evidence.get("after"));
        } catch (Exception e) { throw new IllegalArgumentException("Invalid stored skill", e); }
    }
    private static Map<String, Object> object(JsonReader reader, int depth) throws Exception {
        if (depth > 2) throw new IllegalArgumentException("Depth");
        Map<String, Object> values = new HashMap<>();
        reader.beginObject();
        while (reader.hasNext()) {
            String key = reader.nextName();
            if (values.containsKey(key)) throw new IllegalArgumentException("Duplicate key");
            Object value;
            switch (reader.peek()) {
                case BEGIN_OBJECT: value = object(reader, depth + 1); break;
                case STRING: value = reader.nextString(); break;
                case BOOLEAN: value = reader.nextBoolean(); break;
                case NUMBER:
                    if (!"1".equals(reader.nextString())) throw new IllegalArgumentException("Version number");
                    value = 1; break;
                default: throw new IllegalArgumentException("Unsupported JSON value");
            }
            values.put(key, value);
        }
        reader.endObject();
        return values;
    }
    @SuppressWarnings("unchecked")
    private static Map<String, Object> child(Map<String, Object> root, String key) {
        Object value = root.get(key);
        if (!(value instanceof Map)) throw new IllegalArgumentException("Expected object");
        return (Map<String, Object>)value;
    }
    private static void keys(Map<String, Object> object, Set<String> expected) {
        if (!object.keySet().equals(expected)) throw new IllegalArgumentException("Unknown/missing fields");
    }
}
