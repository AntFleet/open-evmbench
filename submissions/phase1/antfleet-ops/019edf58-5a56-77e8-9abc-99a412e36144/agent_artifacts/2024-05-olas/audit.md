# Audit: 2024-05-olas

# Security Audit Report

## GuardCM: Unguarded timelock `cancel` allows multisig to veto governance
- Location: `GuardCM-flatten.sol` : `checkTransaction`
- Mechanism: The guard only inspects calls to the timelock whose function selector matches `SCHEDULE` or `SCHEDULE_BATCH`. Any other timelock function — most critically `cancel(bytes32)` — passes through unchecked. The community multisig holds the `CANCELLER_ROLE` on the timelock (granted automatically alongside `PROPOSER_ROLE`). Consequently, the multisig can call `cancel` on the timelock to cancel any pending operation that was scheduled by the Governor after a successful governance vote, with no guard restriction.
- Impact: The community multisig can unilaterally veto any governance-approved proposal by cancelling its queued timelock operation, defeating the governance process. This breaks the separation of powers between governance and the multisig.

## OLA: `changeMinter` missing zero-address validation
- Location: `OLA-flatten.sol` : `changeMinter`
- Mechanism: `changeOwner` reverts if `newOwner == address(0)`, but `changeMinter` performs no such check. The owner can set `minter = address(0)`, either accidentally or via a compromised owner account. Once the minter is the zero address, no account satisfies `msg.sender == minter`, so `mint()` permanently reverts for all callers.
- Impact: Permanent disabling of all token minting, bricking the token's inflation mechanism and any downstream systems that rely on minting rewards.

## VerifyBridgedData: Out-of-bounds memory read in `_verifyBridgedData`
- Location: `ProcessBridgedDataArbitrum-flatten.sol` (VerifyBridgedData) : `_verifyBridgedData`
- Mechanism: The function parses a custom binary format using a manually managed index `i`. After reading a `uint32 payloadLength` from the data, it copies `payloadLength` bytes into a new `bytes` array via `payload[j] = data[i + j]`. There is no check that `i + payloadLength <= data.length`. If `payloadLength` exceeds the remaining bytes, the loop reads past the end of the `data` memory allocation, copying zero bytes from uninitialised memory. The resulting `payload` is then verified by `_verifyData`, which only checks the first 4 bytes (the selector). An attacker can craft data where the real selector is authorised but the declared `payloadLength` is larger than the actual content, causing the guard to approve a bridged message whose actual L2 payload differs from what was verified.
- Impact: Bypass of the bridge data whitelist — a bridged transaction with an unauthorised payload could pass verification on L1 and execute arbitrary authorised-selector calls on L2 with attacker-controlled arguments.

## VotingEscrow: Checkpoint loop limited to 255 weeks breaks voting power
- Location: `VotingEscrow-flatten.sol` : `_checkpoint`
- Mechanism: The week-stepping loop in `_checkpoint` iterates at most 255 times (`for (uint256 i = 0; i < 255; ++i)`). If more than 255 weeks (~4.9 years) pass without any checkpoint or user interaction, the loop terminates before reaching `block.timestamp`. The final recorded supply point retains a stale `ts` and `bias`, so `getPastVotes`, `getPastTotalSupply`, and `totalSupplyLockedAtT` all extrapolate from outdated data.
- Impact: After ~5 years of inactivity, all voting-power queries return incorrect values, breaking governance quorum and vote-weight calculations. Users can still withdraw (the `withdraw` path doesn't depend on the loop), but the protocol becomes ungovernable until a manual `checkpoint()` is called — which itself cannot catch up if the gap exceeds 255 weeks.
