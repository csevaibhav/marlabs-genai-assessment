package com.marlabs.gateway.caller;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;

class CallerDirectoryTest {

    private final CallerDirectory directory = new CallerDirectory();

    @Test
    void resolves_known_atlas_employee() {
        CallerIdentity identity = directory.lookup("atlas-employee-01").orElseThrow();
        assertThat(identity.tenant()).isEqualTo("Atlas");
        assertThat(identity.role()).isEqualTo("employee");
    }

    @Test
    void resolves_known_atlas_contractor() {
        CallerIdentity identity = directory.lookup("atlas-contractor-01").orElseThrow();
        assertThat(identity.tenant()).isEqualTo("Atlas");
        assertThat(identity.role()).isEqualTo("contractor");
    }

    @Test
    void resolves_known_boreal_employee() {
        CallerIdentity identity = directory.lookup("boreal-employee-01").orElseThrow();
        assertThat(identity.tenant()).isEqualTo("Boreal");
        assertThat(identity.role()).isEqualTo("employee");
    }

    @Test
    void unknown_caller_is_empty() {
        assertThat(directory.lookup("someone-else-01")).isEmpty();
    }

    @Test
    void null_caller_is_empty() {
        assertThat(directory.lookup(null)).isEmpty();
    }
}
