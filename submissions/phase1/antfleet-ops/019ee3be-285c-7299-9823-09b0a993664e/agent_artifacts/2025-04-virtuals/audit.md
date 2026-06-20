# Audit: 2025-04-virtuals

## Missing prevAgentId update in multi-prompt loop

- Location: contracts/AgentInference.sol : promptMulti
- Mechanism: The function initializes `prevAgentId = 0` and `agentTba = address(0)`, then in the loop only fetches a fresh TBA via `agentNft.virtualInfo(agentId).tba` when `prevAgentId != agentId`; however, `prevAgentId` is never assigned the current `agentId` at the end of each iteration (unlike the equivalent single-prompt path), so the cache condition never re-triggers for any subsequent distinct agentId and the stale `agentTba` is reused for all later `safeTransferFrom` calls.
- Impact: An attacker supplying a mixed `agentIds` array (different agents with non-zero `amounts`) can force tokens belonging to one agent to be transferred into another agent's TBA, permanently misallocating inference payments.

## Incorrect TBA lookup caching leads to fund misdirection

- Location: contracts/AgentInference.sol : promptMulti
- Mechanism: After the first agent change the `if (prevAgentId != agentId)` branch is never taken again, so `token.safeTransferFrom(sender, agentTba, amounts[i])` always uses the TBA of the first distinct agent encountered for every remaining entry regardless of the actual `agentIds[i]` value.
- Impact: Tokens intended for later agents are sent to the wrong TBA; the attacker (or any caller) can therefore drain or redirect payments across agents by ordering the input arrays appropriately.
