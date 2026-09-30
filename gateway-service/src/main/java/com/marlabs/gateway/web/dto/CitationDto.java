package com.marlabs.gateway.web.dto;

import com.fasterxml.jackson.annotation.JsonProperty;

public record CitationDto(
        @JsonProperty("chunk_id") String chunkId,
        String quote
) {
}
