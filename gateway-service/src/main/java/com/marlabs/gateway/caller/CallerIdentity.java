package com.marlabs.gateway.caller;

/**
 * The resolved identity of a caller: tenant and role, as looked up from
 * X-Caller-Id. This is the ONLY source of tenant/role used anywhere in
 * this service -- never a request body field, never document content.
 */
public record CallerIdentity(String callerId, String tenant, String role) {
}
