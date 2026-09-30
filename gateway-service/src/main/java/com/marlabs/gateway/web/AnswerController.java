package com.marlabs.gateway.web;

import com.marlabs.gateway.caller.CallerIdentity;
import com.marlabs.gateway.client.PolicyServiceClient;
import com.marlabs.gateway.web.dto.AnswerRequestBody;
import com.marlabs.gateway.web.dto.AnswerResponseBody;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AnswerController {

    private static final Logger log = LoggerFactory.getLogger(AnswerController.class);

    private final RequestValidation validation;
    private final PolicyServiceClient policyServiceClient;

    public AnswerController(RequestValidation validation, PolicyServiceClient policyServiceClient) {
        this.validation = validation;
        this.policyServiceClient = policyServiceClient;
    }

    @PostMapping("/answer")
    public ResponseEntity<AnswerResponseBody> answer(
            @RequestHeader(value = "X-Caller-Id", required = false) String callerIdHeader,
            @RequestBody(required = false) AnswerRequestBody request
    ) {
        CallerIdentity caller = validation.resolveCaller(callerIdHeader);
        String asOf = request == null ? null : request.asOf();
        String question = request == null ? null : request.question();
        validation.parseAsOf(asOf);
        validation.requireNonEmptyQuestion(question);

        log.info("answer: caller={} tenant={} role={} as_of={}", caller.callerId(), caller.tenant(), caller.role(), asOf);

        AnswerResponseBody response = policyServiceClient.answer(caller.tenant(), caller.role(), asOf, question);
        return ResponseEntity.ok(response);
    }
}
