package com.marlabs.gateway.web.dto;

import java.util.List;

/** Public response body for POST /answer, matching the assessment's
 * citation contract: {status, answer, citations}. */
public record AnswerResponseBody(
        String status,
        String answer,
        List<CitationDto> citations
) {
}
