# Production design note

10,000 requests/day (~7/minute average, bursty around business hours) with
personal information, feeding a slow, partially-documented approval system,
changes the priorities from this exercise in three ways.

**Deployment approach.** Keep the two-service split, but put both behind a
managed container platform (ECS/Fargate or Cloud Run, not raw VMs) with the
gateway as the only externally reachable service and the policy service on a
private network reachable only from the gateway. The synchronous
request/response model from this exercise won't survive a slow downstream
approval system: I'd move batch intake to an async pattern immediately --
`/batches` accepts and returns a batch ID right away, a queue (SQS/RabbitMQ)
feeds workers that call the policy service and the approval system, and a
`GET /batches/{id}` endpoint reports progress. `/answer` can likely stay
synchronous since it doesn't touch the approval system, but needs its own
circuit breaker so a struggling approval system can't back up policy
questions too.

**Security risks, in order.** (1) Personal information at rest and in
transit: everything in submitted documents needs encryption at rest,
field-level redaction in logs (this exercise's "no secrets, no full document
contents by default" logging rule needs to become an enforced default, not a
convention), and a real retention policy -- synthetic data has none, real
employee data can't be kept indefinitely. (2) Authentication: `X-Caller-Id`
as a bare header is a stand-in that must not reach production --
it needs to become a verified identity token (OIDC/JWT from the real IdP),
with tenant/role still resolved server-side, never trusted from the token's
own claims. (3) The approval system is an external dependency of unknown
reliability; treating its failures as "dependency failure, not our policy
finding" (as this exercise already does) has to extend to alerting and
retries with backoff, not silent drops.

**Operational risks.** Silent backlog growth if the approval system is slow
and nothing alerts on queue depth or age; and audit/traceability -- 10k/day
with PII needs structured, correlated logging (batch ID, document ID,
caller, decision) retained for compliance review, which is a bigger ask than
this exercise's basic tracing.

**Before committing to a delivery date I'd need:** the approval system's
actual throughput/SLA and whether it has a webhook or only polling; the real
data-retention and PII-handling requirements from compliance/legal; and
expected peak (not average) request rate, since burst behavior drives the
queue and autoscaling design far more than the daily average does.
