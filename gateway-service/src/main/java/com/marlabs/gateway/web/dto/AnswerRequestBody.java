package com.marlabs.gateway.web.dto;

import com.fasterxml.jackson.annotation.JsonProperty;

/** Public request body for POST /answer. Deliberately has no tenant/role/
 * caller field of its own -- those only ever come from X-Caller-Id. */
public record AnswerRequestBody(
        String question,
        @JsonProperty("as_of") String asOf
) {
}
