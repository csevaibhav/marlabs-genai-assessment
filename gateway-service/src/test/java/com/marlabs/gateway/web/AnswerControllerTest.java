package com.marlabs.gateway.web;

import static org.hamcrest.Matchers.is;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.marlabs.gateway.client.PolicyServiceClient;
import com.marlabs.gateway.web.dto.AnswerResponseBody;
import com.marlabs.gateway.web.dto.CitationDto;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class AnswerControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @MockBean
    private PolicyServiceClient policyServiceClient;

    private static final String VALID_BODY = """
            {"question":"What is my annual certification reimbursement limit?","as_of":"2026-09-21"}
            """;

    @Test
    void missing_caller_header_returns_400() throws Exception {
        mockMvc.perform(post("/answer").contentType(MediaType.APPLICATION_JSON).content(VALID_BODY))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error.code", is("MISSING_CALLER_ID")));
    }

    @Test
    void unknown_caller_returns_401() throws Exception {
        mockMvc.perform(post("/answer")
                        .header("X-Caller-Id", "not-a-real-caller")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(VALID_BODY))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.error.code", is("UNKNOWN_CALLER")));
    }

    @Test
    void invalid_as_of_returns_400() throws Exception {
        mockMvc.perform(post("/answer")
                        .header("X-Caller-Id", "atlas-employee-01")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"question":"limit?","as_of":"21-09-2026"}
                                """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error.code", is("INVALID_AS_OF_DATE")));
    }

    @Test
    void empty_question_returns_400() throws Exception {
        mockMvc.perform(post("/answer")
                        .header("X-Caller-Id", "atlas-employee-01")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"question":"","as_of":"2026-09-21"}
                                """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.error.code", is("INVALID_QUESTION")));
    }

    @Test
    void valid_request_delegates_to_policy_service_and_passes_through_answered() throws Exception {
        when(policyServiceClient.answer(eq("Atlas"), eq("employee"), eq("2026-09-21"), any()))
                .thenReturn(new AnswerResponseBody(
                        "ANSWERED",
                        "The annual certification reimbursement limit for employees is INR 25000.",
                        List.of(new CitationDto("atlas-cert-current", "The annual certification reimbursement limit for employees is INR 25000."))
                ));

        mockMvc.perform(post("/answer")
                        .header("X-Caller-Id", "atlas-employee-01")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(VALID_BODY))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status", is("ANSWERED")))
                .andExpect(jsonPath("$.citations[0].chunk_id", is("atlas-cert-current")));

        verify(policyServiceClient).answer("Atlas", "employee", "2026-09-21", "What is my annual certification reimbursement limit?");
    }

    @Test
    void conflict_status_passes_through_with_null_answer() throws Exception {
        when(policyServiceClient.answer(any(), any(), any(), any()))
                .thenReturn(new AnswerResponseBody("CONFLICT", null, List.of(
                        new CitationDto("atlas-home-office-a", "..."),
                        new CitationDto("atlas-home-office-b", "..."))));

        mockMvc.perform(post("/answer")
                        .header("X-Caller-Id", "atlas-employee-01")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(VALID_BODY))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status", is("CONFLICT")))
                .andExpect(jsonPath("$.answer").doesNotExist());
    }

    @Test
    void dependency_failure_from_policy_service_is_non_2xx() throws Exception {
        when(policyServiceClient.answer(any(), any(), any(), any()))
                .thenThrow(new com.marlabs.gateway.error.ApiException(
                        org.springframework.http.HttpStatus.SERVICE_UNAVAILABLE, "DEPENDENCY_UNAVAILABLE", "down"));

        mockMvc.perform(post("/answer")
                        .header("X-Caller-Id", "atlas-employee-01")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(VALID_BODY))
                .andExpect(status().isServiceUnavailable())
                .andExpect(jsonPath("$.error.code", is("DEPENDENCY_UNAVAILABLE")));
    }
}
