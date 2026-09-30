package com.marlabs.gateway.web;

import static org.hamcrest.Matchers.is;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyList;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.marlabs.gateway.client.PolicyServiceClient;
import com.marlabs.gateway.web.dto.BatchResponseBody;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.mock.web.MockPart;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class BatchControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private PolicyServiceClient policyServiceClient;

    private static final String VALID_METADATA = """
            {"batch_id":"demo-01","as_of":"2026-09-21","documents":[
              {"document_id":"request-01","filename":"request-01.txt"},
              {"document_id":"request-08","filename":"request-08.txt"}
            ]}
            """;

    // Mirrors curl's -F 'metadata={...};type=application/json': a plain part with no filename.
    private static MockPart jsonPart(String name, String json) {
        MockPart part = new MockPart(name, json.getBytes());
        part.getHeaders().set(HttpHeaders.CONTENT_TYPE, MediaType.APPLICATION_JSON_VALUE);
        return part;
    }

    @Test
    void missing_caller_header_fails_whole_batch() throws Exception {
        mockMvc.perform(multipart("/batches")
                        .part(jsonPart("metadata", VALID_METADATA))
                        .file(new MockMultipartFile("files", "request-01.txt", "text/plain", "body".getBytes()))
                        .file(new MockMultipartFile("files", "request-08.txt", "text/plain", new byte[0])))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error.code", is("MISSING_CALLER_ID")));
    }

    @Test
    void duplicate_document_id_fails_whole_batch_non_2xx() throws Exception {
        String dupMetadata = """
                {"batch_id":"demo-01","as_of":"2026-09-21","documents":[
                  {"document_id":"dup","filename":"a.txt"},
                  {"document_id":"dup","filename":"b.txt"}
                ]}
                """;
        mockMvc.perform(multipart("/batches")
                        .part(jsonPart("metadata", dupMetadata))
                        .file(new MockMultipartFile("files", "a.txt", "text/plain", "x".getBytes()))
                        .file(new MockMultipartFile("files", "b.txt", "text/plain", "y".getBytes()))
                        .header("X-Caller-Id", "atlas-employee-01"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error.code", is("DUPLICATE_MANIFEST_ID")));
    }

    @Test
    void missing_file_part_fails_whole_batch_non_2xx() throws Exception {
        mockMvc.perform(multipart("/batches")
                        .part(jsonPart("metadata", VALID_METADATA))
                        .file(new MockMultipartFile("files", "request-01.txt", "text/plain", "body".getBytes()))
                        // request-08.txt deliberately not uploaded
                        .header("X-Caller-Id", "atlas-employee-01"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error.code", is("FILE_MANIFEST_MISMATCH")));
    }

    @Test
    void extra_file_part_fails_whole_batch_non_2xx() throws Exception {
        mockMvc.perform(multipart("/batches")
                        .part(jsonPart("metadata", VALID_METADATA))
                        .file(new MockMultipartFile("files", "request-01.txt", "text/plain", "body".getBytes()))
                        .file(new MockMultipartFile("files", "request-08.txt", "text/plain", new byte[0]))
                        .file(new MockMultipartFile("files", "unexpected.txt", "text/plain", "surprise".getBytes()))
                        .header("X-Caller-Id", "atlas-employee-01"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error.code", is("FILE_MANIFEST_MISMATCH")));
    }

    @Test
    void valid_batch_with_completed_and_failed_items_passes_through() throws Exception {
        when(policyServiceClient.processBatch(eq("Atlas"), eq("employee"), eq("2026-09-21"), eq("demo-01"), anyList(), anyList()))
                .thenReturn(new BatchResponseBody(
                        "demo-01",
                        new BatchResponseBody.Summary(2, 1, 1),
                        List.of(
                                Map.of("document_id", "request-01", "processing_status", "COMPLETED"),
                                Map.of("document_id", "request-08", "processing_status", "FAILED",
                                        "error", Map.of("code", "EMPTY_FILE", "message", "Submitted file is empty."))
                        )
                ));

        mockMvc.perform(multipart("/batches")
                        .part(jsonPart("metadata", VALID_METADATA))
                        .file(new MockMultipartFile("files", "request-01.txt", "text/plain", "body".getBytes()))
                        .file(new MockMultipartFile("files", "request-08.txt", "text/plain", new byte[0]))
                        .header("X-Caller-Id", "atlas-employee-01"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.summary.total", is(2)))
                .andExpect(jsonPath("$.summary.completed", is(1)))
                .andExpect(jsonPath("$.summary.failed", is(1)))
                .andExpect(jsonPath("$.results[1].error.code", is("EMPTY_FILE")));
    }
}
