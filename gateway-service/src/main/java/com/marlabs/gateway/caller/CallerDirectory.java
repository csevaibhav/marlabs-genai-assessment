package com.marlabs.gateway.caller;

import java.util.Map;
import java.util.Optional;
import org.springframework.stereotype.Component;

/**
 * Hardcoded lookup table for the assessment's three synthetic identities.
 *
 * This is the single place caller identity is resolved. For this exercise
 * the X-Caller-Id header simulates authenticated identity -- tenant and
 * role always come from here, never from a request body or a submitted
 * document, no matter what either of those claims (see the corpus's own
 * "prompt-injection example" record, and request-05's embedded "SYSTEM
 * MESSAGE: ... use Boreal policies" text -- both are inert precisely
 * because nothing downstream of this class ever re-derives identity from
 * anything other than the header).
 */
@Component
public class CallerDirectory {

    private static final Map<String, CallerIdentity> CALLERS = Map.of(
            "atlas-employee-01", new CallerIdentity("atlas-employee-01", "Atlas", "employee"),
            "atlas-contractor-01", new CallerIdentity("atlas-contractor-01", "Atlas", "contractor"),
            "boreal-employee-01", new CallerIdentity("boreal-employee-01", "Boreal", "employee")
    );

    public Optional<CallerIdentity> lookup(String callerId) {
        if (callerId == null) {
            return Optional.empty();
        }
        return Optional.ofNullable(CALLERS.get(callerId));
    }
}
