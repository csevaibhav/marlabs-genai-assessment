package com.marlabs.gateway.client;

import com.marlabs.gateway.web.dto.AnswerResponseBody;
import com.marlabs.gateway.web.dto.BatchResponseBody;
import com.marlabs.gateway.web.dto.ManifestEntryDto;
import java.util.List;
import org.springframework.web.multipart.MultipartFile;

/**
 * Boundary to the Python policy-service. This is the only place in the
 * gateway that knows the internal (non-public) request/response shapes.
 * Implementations must translate every dependency failure (timeout,
 * connection refused, non-2xx, malformed body) into a
 * com.marlabs.gateway.error.ApiException so callers never see a raw
 * networking exception.
 */
public interface PolicyServiceClient {

    AnswerResponseBody answer(String tenant, String role, String asOf, String question);

    BatchResponseBody processBatch(
            String tenant,
            String role,
            String asOf,
            String batchId,
            List<ManifestEntryDto> documents,
            List<MultipartFile> files
    );
}
