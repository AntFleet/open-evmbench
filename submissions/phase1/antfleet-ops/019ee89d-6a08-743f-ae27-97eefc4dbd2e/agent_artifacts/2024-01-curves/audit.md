# Audit: 2024-01-curves

## Broken access control: `onlyOwner` / `onlyManager` modifiers are no-ops
- Location: contracts/Security.sol : `onlyOwner`, `onlyManager`
- Mechanism: Both modifiers contain a bare comparison expression statement (`msg.sender == owner;` and `managers[msg.sender] == true;`) instead of a `require`/`if-revert`. Solidity evaluates and discards the boolean, so the modifier body reduces to just `_;` and enforces nothing. Every privileged function gated by these modifiers is therefore callable by any address: `transferOwnership`, `setManager`, `setProtocolFeePercent`, `setFeeRedistributor`, `setMaxFeePercent`, `setExternalFeePercent`, `setERC20Factory`, and `FeeSplitter.addFees` / `FeeSplitter.onBalanceChange`.
- Impact: Any attacker can call `transferOwnership` to seize the contract and `setProtocolFeePercent(maxPct, attackerAddress)` to redirect all protocol fees to themselves, fully compromising the protocol.

## Fee theft: token transfers bypass fee-offset snapshotting, letting recipients over-claim historical fees
- Location: contracts/Curves.sol : `_transfer` / `transferCurvesToken` (interacting with contracts/FeeSplitter.sol : `claimFees`)
- Mechanism: `FeeSplitter` uses a dividend-per-token model where `claimable = (cumulativeFeePerToken - userFeeOffset[user]) * balance / PRECISION + unclaimedFees`. The offset is only ever updated inside `onBalanceChange` (called from `_transferFees` on buy/sell). The `_transfer` path (`transferCurvesToken`, `transferAllCurvesTokens`, `withdraw`, `deposit`) never notifies `FeeSplitter`, so a fresh recipient keeps `userFeeOffset == 0` while its live `balanceOf` (read directly from `curves.curvesTokenBalance`) is now positive. Its claimable becomes `cumulativeFeePerToken * balance / PRECISION` — fees accrued over the entire history before it ever held the token. An attacker buys/holds in address A, transfers the tokens to a fresh address B (offset 0), and B calls `claimFees`.
- Impact: The fresh recipient drains far more than its fair share of the holder-fee pool, stealing ETH that belongs to other holders and rendering the splitter insolvent (first claimer wins, others' `transfer` reverts for lack of balance).

## Holder fees forfeited: `onBalanceChange` resets the fee offset without crediting owed fees
- Location: contracts/FeeSplitter.sol : `onBalanceChange`
- Mechanism: `onBalanceChange` overwrites `data.userFeeOffset[account] = data.cumulativeFeePerToken` but, unlike `updateFeeCredit`, it never first credits the pending `(cumulativeFeePerToken - oldOffset) * balance` into `unclaimedFees`. It is invoked from `_transferFees` on every buy and sell of an existing holder, so any fees that accrued on the holder's prior balance since their last snapshot are silently zeroed out by advancing the offset past them.
- Impact: A holder who buys or sells any amount permanently loses all of their accrued-but-unclaimed holder fees, which become stranded in the contract.

## Protocol fee charged to sellers is never forwarded and is permanently locked
- Location: contracts/Curves.sol : `_transferFees` (sell branch)
- Mechanism: On a sell, `firstDestination` is `msg.sender` and receives `sellValue = price - protocolFee - subjectFee - referralFee - holderFee`. The subject, referral, and holder fees are subsequently paid out, but `protocolFee` is deducted from the seller's proceeds and never sent to `feesEconomics.protocolFeeDestination` (only the buy branch pays it). Since the contract exposes no mechanism to withdraw raw ETH, this withheld amount accumulates and is irrecoverable.
- Impact: Sellers are overcharged by the protocol fee on every sale and that ETH is permanently locked in the contract, lost to both the seller and the protocol.

## Denial of service: a subject that rejects ETH traps all of its holders
- Location: contracts/Curves.sol : `_transferFees` (`curvesTokenSubject.call{value: subjectFee}`)
- Mechanism: Both buys and sells route `subjectFee` to `curvesTokenSubject` via a raw `call`, and a failed transfer reverts the whole trade with `CannotSendFunds`. The subject address is fixed at first buy and can be a contract. A malicious subject can accept ETH long enough to attract buyers, then change to reject all incoming ETH, after which every `sellCurvesToken` call reverts because the `subjectFee` transfer fails.
- Impact: All holders of that subject's token are permanently unable to sell and have their invested ETH trapped in the curve.

## Griefing DoS: unsolicited transfers bloat `ownedCurvesTokenSubjects`, breaking a victim's transfers and buys
- Location: contracts/Curves.sol : `_addOwnedCurvesTokenSubject` / `transferCurvesToken`
- Mechanism: `_addOwnedCurvesTokenSubject` linearly scans the recipient's entire `ownedCurvesTokenSubjects` array on every incoming transfer and on every first-time buy, and the array is never pruned. Because the first token of any new subject costs `getPrice(0,1) == 0`, an attacker can cheaply create many subjects (one per controlled address) and `transferCurvesToken` one unit of each to a victim, forcing unbounded growth of the victim's array. Once large enough, the O(n) scan exceeds the block gas limit.
- Impact: The victim can no longer receive token transfers, buy a first token of any new subject, or run `transferAllCurvesTokens`, as each operation runs out of gas — a permanent, attacker-induced denial of service against a chosen address.

