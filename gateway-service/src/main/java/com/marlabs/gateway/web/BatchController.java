package com.marlabs.gateway.web;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.exc.MismatchedInputException;
import com.marlabs.gateway.caller.CallerIdentity;
import com.marlabs.gateway.client.PolicyServiceClient;
import com.marlabs.gateway.error.ApiException;
import com.marlabs.gateway.web.dto.BatchMetadataBody;
import com.marlabs.gateway.web.dto.BatchResponseBody;
import com.marlabs.gateway.web.dto.ManifestEntryDto;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@RestController
public class BatchController {

    private static final Logger log = LoggerFactory.getLogger(BatchController.class);

    private final RequestValidation validation;
    private final PolicyServiceClient policyServiceClient;
    private final ObjectMapper objectMapper;

    public BatchController(RequestValidation validation, PolicyServiceClient policyServiceClient, ObjectMapper objectMapper) {
        this.validation = validation;
        this.policyServiceClient = policyServiceClient;
        this.objectMapper = objectMapper;
    }

    @PostMapping(value = "/batches", consumes = "multipart/form-data")
    public ResponseEntity<BatchResponseBody> submitBatch(
            @RequestHeader(value = "X-Caller-Id", required = false) String callerIdHeader,
            @RequestParam("metadata") String metadataJson,
            @RequestPart(value = "files", required = false) List<MultipartFile> files
    ) {
        CallerIdentity caller = validation.resolveCaller(callerIdHeader);

        BatchMetadataBody metadata = parseMetadata(metadataJson);
        validation.parseAsOf(metadata.asOf());
        if (metadata.documents() == null || metadata.documents().isEmpty()) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "EMPTY_MANIFEST", "documents must contain at least one entry.");
        }
        if (files == null) {
            files = List.of();
        }

        validateManifestUniqueness(metadata.documents());
        validateFilesMatchManifest(metadata.documents(), files);

        log.info(
                "batch: caller={} tenant={} role={} batch_id={} as_of={} items={}",
                caller.callerId(), caller.tenant(), caller.role(), metadata.batchId(), metadata.asOf(), metadata.documents().size()
        );

        BatchResponseBody response = policyServiceClient.processBatch(
                caller.tenant(), caller.role(), metadata.asOf(), metadata.batchId(), metadata.documents(), files
        );
        return ResponseEntity.ok(response);
    }

    private BatchMetadataBody parseMetadata(String metadataJson) {
        try {
            BatchMetadataBody metadata = objectMapper.readValue(metadataJson, BatchMetadataBody.class);
            if (metadata.batchId() == null || metadata.batchId().isBlank()) {
                throw new ApiException(HttpStatus.BAD_REQUEST, "INVALID_METADATA", "batch_id is required.");
            }
            return metadata;
        } catch (ApiException ex) {
            throw ex;
        } catch (MismatchedInputException ex) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "INVALID_METADATA", "metadata JSON does not match the expected shape.");
        } catch (Exception ex) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "INVALID_METADATA", "metadata part is not valid JSON.");
        }
    }

    private void validateManifestUniqueness(List<ManifestEntryDto> documents) {
        Set<String> ids = new HashSet<>();
        Set<String> filenames = new HashSet<>();
        for (ManifestEntryDto entry : documents) {
            if (entry.documentId() == null || entry.filename() == null) {
                throw new ApiException(HttpStatus.BAD_REQUEST, "INVALID_METADATA", "each document entry requires document_id and filename.");
            }
            if (!ids.add(entry.documentId())) {
                throw new ApiException(HttpStatus.BAD_REQUEST, "DUPLICATE_MANIFEST_ID", "document_id must be unique within the manifest: " + entry.documentId());
            }
            if (!filenames.add(entry.filename())) {
                throw new ApiException(HttpStatus.BAD_REQUEST, "DUPLICATE_MANIFEST_FILENAME", "filename must be unique within the manifest: " + entry.filename());
            }
        }
    }

    private void validateFilesMatchManifest(List<ManifestEntryDto> documents, List<MultipartFile> files) {
        Set<String> manifestFilenames = documents.stream().map(ManifestEntryDto::filename).collect(Collectors.toSet());
        Set<String> uploadedFilenames = new HashSet<>();
        for (MultipartFile file : files) {
            String name = file.getOriginalFilename();
            if (!uploadedFilenames.add(name)) {
                throw new ApiException(HttpStatus.BAD_REQUEST, "DUPLICATE_FILE_PART", "duplicate uploaded filename: " + name);
            }
        }
        if (!manifestFilenames.equals(uploadedFilenames)) {
            throw new ApiException(
                    HttpStatus.BAD_REQUEST,
                    "FILE_MANIFEST_MISMATCH",
                    "uploaded files must match the manifest exactly (no missing or extra file parts)."
            );
        }
    }
}
