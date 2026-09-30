package com.marlabs.gateway.web;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.marlabs.gateway.caller.CallerDirectory;
import com.marlabs.gateway.error.ApiException;
import java.time.LocalDate;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;

class RequestValidationTest {

    private final RequestValidation validation = new RequestValidation(new CallerDirectory());

    @Test
    void missing_caller_header_is_rejected_with_400() {
        assertThatThrownBy(() -> validation.resolveCaller(null))
                .isInstanceOfSatisfying(ApiException.class, ex -> {
                    assertThat(ex.getStatus()).isEqualTo(HttpStatus.BAD_REQUEST);
                    assertThat(ex.getCode()).isEqualTo("MISSING_CALLER_ID");
                });
    }

    @Test
    void unknown_caller_is_rejected_with_401() {
        assertThatThrownBy(() -> validation.resolveCaller("nobody-here-01"))
                .isInstanceOfSatisfying(ApiException.class, ex -> {
                    assertThat(ex.getStatus()).isEqualTo(HttpStatus.UNAUTHORIZED);
                    assertThat(ex.getCode()).isEqualTo("UNKNOWN_CALLER");
                });
    }

    @Test
    void known_caller_resolves() {
        assertThat(validation.resolveCaller("atlas-employee-01").tenant()).isEqualTo("Atlas");
    }

    @Test
    void valid_as_of_parses() {
        assertThat(validation.parseAsOf("2026-09-21")).isEqualTo(LocalDate.of(2026, 9, 21));
    }

    @Test
    void missing_as_of_is_rejected() {
        assertThatThrownBy(() -> validation.parseAsOf(null))
                .isInstanceOfSatisfying(ApiException.class, ex -> assertThat(ex.getCode()).isEqualTo("MISSING_AS_OF"));
    }

    @Test
    void malformed_as_of_is_rejected() {
        for (String bad : new String[] {"21-09-2026", "2026/09/21", "not-a-date", "2026-13-40"}) {
            assertThatThrownBy(() -> validation.parseAsOf(bad))
                    .as("expected rejection for %s", bad)
                    .isInstanceOfSatisfying(ApiException.class, ex -> assertThat(ex.getCode()).isEqualTo("INVALID_AS_OF_DATE"));
        }
    }

    @Test
    void blank_question_is_rejected() {
        assertThatThrownBy(() -> validation.requireNonEmptyQuestion("   "))
                .isInstanceOfSatisfying(ApiException.class, ex -> assertThat(ex.getCode()).isEqualTo("INVALID_QUESTION"));
    }

    @Test
    void non_empty_question_passes_through() {
        assertThat(validation.requireNonEmptyQuestion("hi")).isEqualTo("hi");
    }
}
