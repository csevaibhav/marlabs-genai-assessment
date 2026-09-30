package com.marlabs.gateway.client;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.marlabs.gateway.error.ApiException;
import com.marlabs.gateway.web.dto.AnswerResponseBody;
import com.marlabs.gateway.web.dto.BatchMetadataBody;
import com.marlabs.gateway.web.dto.BatchResponseBody;
import com.marlabs.gateway.web.dto.ManifestEntryDto;
import java.io.IOException;
import java.net.http.HttpClient;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.core.io.ByteArrayResource;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.http.client.MultipartBodyBuilder;
import org.springframework.stereotype.Component;
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientResponseException;
import org.springframework.web.multipart.MultipartFile;

@Component
public class PolicyServiceClientImpl implements PolicyServiceClient {

    private static final Logger log = LoggerFactory.getLogger(PolicyServiceClientImpl.class);

    private final RestClient restClient;
    private final ObjectMapper objectMapper;

    @Autowired
    public PolicyServiceClientImpl(PolicyServiceProperties props, ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;

        HttpClient jdkClient = HttpClient.newBuilder()
                .connectTimeout(Duration.ofMillis(props.getConnectTimeoutMs()))
                .build();
        JdkClientHttpRequestFactory requestFactory = new JdkClientHttpRequestFactory(jdkClient);
        requestFactory.setReadTimeout(Duration.ofMillis(props.getReadTimeoutMs()));

        this.restClient = RestClient.builder()
                .baseUrl(props.getBaseUrl())
                .requestFactory(requestFactory)
                .build();
    }

    @Override
    public AnswerResponseBody answer(String tenant, String role, String asOf, String question) {
        Map<String, Object> body = Map.of(
                "tenant", tenant,
                "role", role,
                "as_of", asOf,
                "question", question
        );
        try {
            return restClient.post()
                    .uri("/internal/answer")
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(body)
                    .retrieve()
                    .body(AnswerResponseBody.class);
        } catch (RestClientResponseException ex) {
            log.warn("policy-service /internal/answer returned {}", ex.getStatusCode());
            throw dependencyFailure(ex);
        } catch (ResourceAccessException ex) {
            log.warn("policy-service unreachable for /internal/answer: {}", ex.getMessage());
            throw unavailable();
        }
    }

    @Override
    public BatchResponseBody processBatch(
            String tenant, String role, String asOf, String batchId,
            List<ManifestEntryDto> documents, List<MultipartFile> files
    ) {
        try {
            BatchMetadataBody metadata = new BatchMetadataBody(batchId, asOf, documents);
            // tenant/role travel alongside batch_id/as_of/documents as part
            // of the internal contract only; the public contract never
            // exposes them (they come from the header, not from the caller).
            Map<String, Object> internalMetadata = Map.of(
                    "batch_id", metadata.batchId(),
                    "tenant", tenant,
                    "role", role,
                    "as_of", metadata.asOf(),
                    "documents", metadata.documents()
            );
            String metadataJson = objectMapper.writeValueAsString(internalMetadata);

            MultipartBodyBuilder builder = new MultipartBodyBuilder();
            builder.part("metadata", metadataJson, MediaType.APPLICATION_JSON);
            for (MultipartFile file : files) {
                ByteArrayResource resource = new ByteArrayResource(file.getBytes()) {
                    @Override
                    public String getFilename() {
                        return file.getOriginalFilename();
                    }
                };
                builder.part("files", resource, MediaType.APPLICATION_OCTET_STREAM);
            }

            return restClient.post()
                    .uri("/internal/process-batch")
                    .contentType(MediaType.MULTIPART_FORM_DATA)
                    .body(builder.build())
                    .retrieve()
                    .body(BatchResponseBody.class);
        } catch (IOException ex) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "UNREADABLE_UPLOAD", "One or more uploaded files could not be read.");
        } catch (RestClientResponseException ex) {
            log.warn("policy-service /internal/process-batch returned {}", ex.getStatusCode());
            if (ex.getStatusCode().is4xxClientError()) {
                throw new ApiException(HttpStatus.BAD_REQUEST, "BATCH_VALIDATION_FAILED", "Batch manifest is invalid.");
            }
            throw dependencyFailure(ex);
        } catch (ResourceAccessException ex) {
            log.warn("policy-service unreachable for /internal/process-batch: {}", ex.getMessage());
            throw unavailable();
        }
    }

    private ApiException dependencyFailure(RestClientResponseException ex) {
        return new ApiException(HttpStatus.BAD_GATEWAY, "DEPENDENCY_FAILURE",
                "Answer generation failed due to a technical error. Please retry.");
    }

    private ApiException unavailable() {
        return new ApiException(HttpStatus.SERVICE_UNAVAILABLE, "DEPENDENCY_UNAVAILABLE",
                "The policy service is currently unavailable.");
    }
}
