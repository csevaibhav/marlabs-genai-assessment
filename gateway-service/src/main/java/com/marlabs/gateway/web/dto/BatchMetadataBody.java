package com.marlabs.gateway.web.dto;

import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;

/** The JSON metadata part of the multipart POST /batches request. */
public record BatchMetadataBody(
        @JsonProperty("batch_id") String batchId,
        @JsonProperty("as_of") String asOf,
        List<ManifestEntryDto> documents
) {
}
