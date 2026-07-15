# Governance Mappings

These mappings explain how Decision Receipt fields can support governance questions. They are not certification claims, legal opinions, or evidence that a workflow complies with a named law or framework.

| Framework | Governance question | What a receipt can make inspectable |
|---|---|---|
| NIST AI RMF | Are accountability structures, risk evidence, and controls visible? | who had authority, what evidence existed, and what control gated the action |
| EU AI Act | Can record-keeping, technical documentation, and human oversight be demonstrated? | a reconstructable decision path and the context, authority, scope, and stop-power available to the human reviewer |
| India MeitY AI Governance Guidelines | Can human oversight and deployer accountability be demonstrated proportionally? | a replayable record of what the human could see, understand, stop, and own |
| OWASP Top 10 for LLM Applications | Where did model output cross a trust boundary? | the evidence, authority, boundary, and execution state around excessive agency, injection, or poisoning risks |

A receipt is one evidence object inside a wider governance program. The surrounding organization must still authenticate identities, define valid authority, evaluate evidence quality, operate controls, investigate incidents, and satisfy applicable legal obligations.

## Use in an assessment

For one consequential workflow, ask:

1. Which receipt fields are available today?
2. Which fields are asserted but not independently verified?
3. Which authority decision is enforced by another system?
4. Which evidence can change between review and execution?
5. Who remains accountable after automation acts?
6. What event causes the decision to be reopened or reviewed?

The result is a workflow-level evidence map, not a compliance certificate.
