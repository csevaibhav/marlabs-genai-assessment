package com.marlabs.gateway.web.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;
import java.util.Map;

public record BatchResponseBody(
        @JsonProperty("batch_id") String batchId,
        Summary summary,
        // Each item's nested shape (extracted/field_evidence/policy/issues/...)
        // is passed through as-is from the policy service -- documented in the
        // README rather than re-typed field by field here.
        List<Map<String, Object>> results
) {
    public record Summary(int total, int completed, int failed) {
    }
}
