package com.marlabs.gateway.web.dto;

import com.fasterxml.jackson.annotation.JsonProperty;

public record ManifestEntryDto(
        @JsonProperty("document_id") String documentId,
        String filename
) {
}
