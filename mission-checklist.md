# Mission Checklist: FinCore Banking API

## Tier 1: Research & Compliance
| ID | Target | Priority | Risk | Status |
|----|--------|----------|------|--------|
| RES-001 | Analyze `sut-server/docs/api-spec.md` vs `sut-server/server.js` implementation gaps | P0 | High | ✅ Completed |
| RES-002 | Verify PCI-DSS/PII compliance in `/accounts` and `/admin/debug` responses | P0 | Severe | ✅ Completed |

## Tier 2: Smoke Tests
| ID | Target | Priority | Risk | Status |
|----|--------|----------|------|--------|
| SMK-001 | Verify `/health` returns 200 OK | P0 | Low | ✅ Completed |
| SMK-002 | Verify Authentication (valid vs invalid tokens) | P0 | Critical | ✅ Completed |
| SMK-003 | Test Happy Path: Transfer funds between Alice and Bob | P1 | High | ✅ Completed |

## Tier 3: Security & Edge Cases
| ID | Target | Priority | Risk | Status |
|----|--------|----------|------|--------|
| SEC-001 | Test IDOR: Can Alice view Bob's transactions? (`/accounts/102/transactions`) | P0 | Severe | ✅ Completed |
| SEC-002 | Test Admin Access: Is `/admin/debug` accessible with standard user token? | P0 | Critical | ✅ Completed |
| SEC-003 | Test XSS: Reflected injection in `/utils/echo?msg=<script>...` | P1 | High | ✅ Completed |
| SEC-004 | Test Transaction Integrity: Negative amounts or insufficient funds | P1 | High | ✅ Completed |

## Tier 4: Reliability & Backlog Expansion
| ID | Target | Priority | Risk | Status |
|----|--------|----------|------|--------|
| REL-001 | Test idempotency enforcement: Send identical transfer requests with same Idempotency-Key header, verify only one transfer occurs and second request returns original transaction or 409 conflict without double-processing | P0 | Critical | ☐ Not Started |
| REL-002 | Test concurrent transfer race condition: Execute simultaneous transfers from same source account to multiple recipients within 100ms window, verify final balances match expected values and no overdrafts occur | P0 | Critical | ☐ Not Started |
| REL-003 | Test account enumeration via transfer validation: Attempt transfers to non-existent account IDs (1000-1010 range), verify consistent error responses that don't reveal whether account IDs are valid | P1 | High | ☐ Not Started |
| INF-004 | Test rate limiting enforcement: Execute 20+ rapid transfer requests within 30 seconds, verify API returns 429 Too Many Requests after threshold and blocks subsequent requests | P1 | High | ☐ Not Started |
| INF-005 | Test zero-value transfer validation: Send transfer requests with amount=0.00, verify system consistently rejects with 400 error and does not create zero-value transaction records | P1 | Medium | ☐ Not Started |
| INF-006 | Test PII redaction in audit trails: Perform authenticated transfer, query any available audit or debug endpoints, verify full account numbers and CVV are masked (e.g., ****1234) and not exposed in plaintext | P0 | Severe | ☐ Not Started |
| INF-007 | Test decimal precision boundary: Execute transfers with varying decimal precision (0.01, 0.001, 0.0001, 0.00001), verify system handles fractional cents correctly and maintains consistent precision in transaction records and account balances | P1 | High | ☐ Not Started |
| INF-008 | Test account state transition during transfer: Initiate transfer, then freeze source account mid-flight, verify system either completes transfer atomically or rejects with consistent error and does not leave funds in intermediate state | P1 | High | ☐ Not Started |
| INF-009 | Test transfer description field length limits: Send transfer with description field containing 10KB+ of text, verify system handles oversized input gracefully without truncation issues, server errors, or logging sensitive data | P1 | Medium | ☐ Not Started |
