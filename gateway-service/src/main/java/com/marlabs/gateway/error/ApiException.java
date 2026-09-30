package com.marlabs.gateway.error;

import org.springframework.http.HttpStatus;

/** A request-validation or dependency failure with a stable code, a safe
 * (non-leaking) message, and the HTTP status it must be reported as. */
public class ApiException extends RuntimeException {

    private final HttpStatus status;
    private final String code;

    public ApiException(HttpStatus status, String code, String message) {
        super(message);
        this.status = status;
        this.code = code;
    }

    public HttpStatus getStatus() {
        return status;
    }

    public String getCode() {
        return code;
    }
}
