package com.marlabs.gateway.web;

import com.marlabs.gateway.caller.CallerDirectory;
import com.marlabs.gateway.caller.CallerIdentity;
import com.marlabs.gateway.error.ApiException;
import java.time.LocalDate;
import java.time.format.DateTimeFormatter;
import java.time.format.DateTimeParseException;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;

/**
 * Shared request-validation rules for both public endpoints. Kept in one
 * place so /answer and /batches can never silently drift apart on what
 * counts as a valid caller or a valid as_of date.
 */
@Component
public class RequestValidation {

    private static final DateTimeFormatter AS_OF_FORMAT = DateTimeFormatter.ISO_LOCAL_DATE; // YYYY-MM-DD

    private final CallerDirectory callerDirectory;

    public RequestValidation(CallerDirectory callerDirectory) {
        this.callerDirectory = callerDirectory;
    }

    public CallerIdentity resolveCaller(String callerIdHeader) {
        if (callerIdHeader == null || callerIdHeader.isBlank()) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "MISSING_CALLER_ID", "X-Caller-Id header is required.");
        }
        return callerDirectory.lookup(callerIdHeader)
                .orElseThrow(() -> new ApiException(HttpStatus.UNAUTHORIZED, "UNKNOWN_CALLER", "X-Caller-Id is not recognized."));
    }

    public LocalDate parseAsOf(String asOf) {
        if (asOf == null || asOf.isBlank()) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "MISSING_AS_OF", "as_of is required.");
        }
        try {
            return LocalDate.parse(asOf, AS_OF_FORMAT);
        } catch (DateTimeParseException ex) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "INVALID_AS_OF_DATE", "as_of must be a valid date in YYYY-MM-DD format.");
        }
    }

    public String requireNonEmptyQuestion(String question) {
        if (question == null || question.isBlank()) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "INVALID_QUESTION", "question must be a non-empty string.");
        }
        return question;
    }
}
