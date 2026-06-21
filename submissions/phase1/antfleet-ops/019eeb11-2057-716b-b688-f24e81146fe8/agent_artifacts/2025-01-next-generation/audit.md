# Audit: 2025-01-next-generation
# Scaffold: antfleet-two-model-multishot-v3p1-cli (claude=claude-opus-4-8, codex=gpt-5.5; shots_per_model=3; total_reports=6; effort_claude=xhigh, effort_codex=high)

## Consensus findings

## Forwarder trusts a caller-supplied EIP-712 `domainSeparator` → cross-domain / cross-chain signature replay
*(consensus, 5 of 6 reports)*
- Location: `contracts/Forwarder.sol` : `execute` / `verify` / `_verifySig`
- Mechanism: The EIP-712 digest is built from a `domainSeparator` passed in as caller calldata (`keccak256(abi.encodePacked("\x19\x01", domainSeparator, keccak256(_getEncoded(...))))`). The contract only checks that `requestTypeHash` is registered in `typeHashes`; it never derives or verifies the domain separator against its own name/version/`block.chainid`/`address(this)`. The only replay protection is the per-sender `nonces[req.from]` counter, local to this deployment.
- Impact: A signature a victim produced over the `ForwardRequest` fields under a colliding domain (same forwarder address on another chain if chainId is omitted, a redeployment, or another dApp reusing the generic request type if `verifyingContract` is omitted) can be replayed here while the victim's nonce still matches, forcing a `transfer` from the victim. Security rests entirely on every off-chain client always pinning this forwarder + chain.
- Reviewer disagreement: None — the one report that did not surface it (opus shot 2) simply never addressed the domain-separator path.

## Transaction fee is charged beyond the spender's allowance / signed value in `transferFrom` (and `transferWithAuthorization`)
*(consensus, 5 of 6 reports)*
- Location: `contracts/Token.sol` : `transferFrom` / `transferSanity` / `_payTxFee` (`_update(from, _feesFaucet, txFees)`), and `transferWithAuthorization`
- Mechanism: `transferSanity` calls `_payTxFee(sender, amount)`, which moves `txFees` out of `sender` with a raw `_update` that touches no allowance. Only afterward does `super.transferFrom` run `_spendAllowance(sender, spender, amount)` for `amount` alone. The owner is debited `amount + txFees` while only `amount` is counted against the allowance. The same shape exists in `transferWithAuthorization`, whose EIP-712 message commits only to `value` yet is charged an additional unsigned `txFees`.
- Impact: A spender approved for exactly `A` (e.g. a DEX router) causes the owner to lose `A + fee` — value redirected to the admin-controlled `_feesFaucet` beyond consent. Combined with a 100% fee rate, a single `transferFrom` can drain up to ~`2A`. A spender pulling the full approved amount is also silently DoS'd when the owner lacks a fee buffer.
- Reviewer disagreement: None — the one report that did not surface it (gpt shot 3) only audited the forwarder layer.

## Meta-tx / gasless fee *amount* is unsigned and read from mutable state at execution time
*(consensus, 5 of 6 reports)*
- Location: `contracts/Token.sol` : `_payTxFee` / `payGaslessBasefee` / `transferWithAuthorization`; `contracts/ERC20MetaTxUpgradeable.sol` : `permit` / `transferWithAuthorization`
- Mechanism: Signed payloads (permit / TWA / `ForwardRequest`) commit only to `value`; the actual cost is `value + calculateTxFee(value) + _gaslessBasefee`, where `_txfeeRate` and `_gaslessBasefee` are read from mutable admin storage at execution time. There is no max-fee field in any signed struct, and the relayer chooses when to submit.
- Impact: A signer can be charged more than they could anticipate — an admin can raise the rate, or a relayer can wait, between signing and relaying. If the holder's balance is exactly `value`, `_payTxFee` reverts, so a legitimately signed authorization can become unexecutable (griefing).
- Reviewer disagreement: opus shots 1–3 frame this as admin-trust-dependent / lower severity rather than a roleless exploit.

## Gasless basefee recipient (paymaster) is the arbitrary caller of `execute` — front-run to collect the fee
*(consensus, 4 of 6 reports)*
- Location: `contracts/Forwarder.sol` : `execute`; `contracts/Token.sol` : `payGaslessBasefee` (`_eurf.payGaslessBasefee(req.from, _msgSender())`)
- Mechanism: The signed `ForwardRequest` does not include the basefee recipient. After executing the forwarded transfer, `execute` calls `payGaslessBasefee(req.from, _msgSender())`, making the basefee recipient whoever submitted the transaction.
- Impact: Anyone who obtains or observes a valid unused signed meta-tx can submit it first and receive the signer's `_gaslessBasefee`, even if the signer intended a different relayer. Preconditions: `_gaslessBasefee > 0`, sufficient signer balance, access to the signed request.
- Reviewer disagreement: None direct; opus reports fold the relayer-profit observation into the broader unsigned-fee finding above.

## `setTxFeeRate` admits a 100% fee rate (`FEE_RATIO`)
*(consensus, 3 of 6 reports)*
- Location: `contracts/FeesHandlerUpgradeable.sol` : `setTxFeeRate` (`if (newTxFeeRate > FEE_RATIO || newTxFeeRate < 0)`)
- Mechanism: The guard rejects only rates strictly greater than `FEE_RATIO` (10000), so `newTxFeeRate == 10000` (100%) is accepted; the `< 0` clause is dead code for a `uint256`. At 100%, `calculateTxFee(amount) == amount`, so `_payTxFee` requires `balanceOf(from) >= 2·amount`.
- Impact: A single ADMIN call (or compromised ADMIN) makes the token effectively non-transferable for any holder without a 2× buffer (always reverts `BalanceTooLow`) and turns every funded transfer into a 100% tax to `_feesFaucet`. Amplifies the allowance/signed-value over-charge above.
- Reviewer disagreement: All three finders note it is ADMIN-gated, hence lower severity.

## `calculateTxFee` floor division → fee rounds to zero / fee evasion by splitting
*(consensus, 2 of 6 reports)*
- Location: `contracts/FeesHandlerUpgradeable.sol` : `calculateTxFee` (`(txAmount * _txfeeRate) / FEE_RATIO`); `contracts/Token.sol` : `transferSanity`
- Mechanism: Multiply-then-divide with truncation and no minimum fee or remainder accumulation. Any transfer where `txAmount * _txfeeRate < FEE_RATIO` floors the fee to 0; rounding always favors the payer.
- Impact: Dust-sized transfers move value fee-free, and a larger transfer can be split into many sub-threshold transfers to avoid most/all fees, eroding fee revenue. With 6 decimals the per-tx threshold is tiny, so wholesale evasion is marginal but real.
- Reviewer disagreement: None.

## Trusted-forwarder `_msgSender()` spoofing threatens every access-controlled function
*(consensus, 2 of 6 reports)*
- Location: `contracts/ERC20MetaTxUpgradeable.sol` : `_msgSender()` override; `contracts/Token.sol` : `setTrustedForwarder`; init grants in `ERC20AdminUpgradeable` / `ERC20ControlerMinterUpgradeable`
- Mechanism: The ERC-2771 override returns the last 20 calldata bytes whenever `msg.sender == _trustedForwarder`, and this `_msgSender()` feeds every `onlyRole(...)` check (mint, blacklist, pause, forceTransfer, setOwner, `_authorizeUpgrade`). The shipped `Forwarder.execute` is safe only because it hard-restricts forwarded calls to `req.to == _eurfAddress` and the `transfer(address,uint256)` selector. (Opus shot 1 adds that `ADMIN`/`MASTER_MINTER` are granted to `address(0)` at init, which would be the impersonation target for a more permissive forwarder.)
- Impact: If an admin ever sets a forwarder that relays arbitrary selectors, an attacker can append a privileged address to the calldata and impersonate admin/minter/owner — full bypass of access control. A fragile, high-blast-radius coupling rather than a live exploit today.
- Reviewer disagreement: Both finders agree it is latent / not exploitable with the shipped forwarder.

## Front-runnable initializers → proxy takeover
*(consensus, 2 of 6 reports)*
- Location: `contracts/Token.sol` : `initialize`; `contracts/Forwarder.sol` : `initialize`
- Mechanism: `EURFToken.initialize()` grants `OWNER`/`DEFAULT_ADMIN_ROLE` to `msg.sender`, and `Forwarder.initialize(token)` sets the owner to `_msgSender()`; both are guarded only by `initializer` (the implementation constructor is locked, but who calls the proxy's `initialize` is not constrained). If deployment is not atomic, any observer can call `initialize` first.
- Impact: The winner becomes `OWNER`, then self-appoints `ADMIN`/`MASTER_MINTER`, mints arbitrarily, blacklists/force-transfers, and upgrades the implementation; for the forwarder, registers arbitrary request types. Full takeover, contingent on a non-atomic deploy.
- Reviewer disagreement: Both note severity hinges on the deployment script.

## Missing storage gaps in the base upgradeable contracts (UUPS storage-layout corruption)
*(consensus, 2 of 6 reports)*
- Location: `contracts/ERC20MetaTxUpgradeable.sol`, `ERC20AdminUpgradeable.sol`, `ERC20ControlerMinterUpgradeable.sol`, `FeesHandlerUpgradeable.sol` (no `__gap`); only `EURFToken` reserves `uint256[49] __gap`
- Mechanism: `EURFToken` linearizes these parents' storage sequentially, and the single `__gap` sits at the end of the most-derived contract, protecting only appends to `EURFToken`, not to any parent.
- Impact: A future upgrade adding one state variable to any base contract shifts every subsequent slot, corrupting `_blacklist`, `minterAllowed`, the fee configuration, and AccessControl role data — silently un-blacklisting accounts, resurrecting minter allowances, or repointing the fee faucet. Critical latent risk given upgradeability is the design goal.
- Reviewer disagreement: None (one report lists it as a primary finding, the other as a minor observation).

## `FeesPaid` event/state desync when the fee faucet is unset
*(consensus, 2 of 6 reports)*
- Location: `contracts/Token.sol` : `_payTxFee`
- Mechanism: When `_feesFaucet == address(0)`, the `_update` transfer is skipped but `emit FeesPaid(from, txFees)` still fires with the full computed fee, and the balance precondition `balanceOf(from) >= txFees + txAmount` is still enforced.
- Impact: Off-chain indexers trusting `FeesPaid` over-count collected fees while the faucet is unset, and transfers can revert (`BalanceTooLow`) for balances that should suffice. Low severity (event-vs-storage divergence, no theft).
- Reviewer disagreement: None.

## Blacklist not enforced on inbound / fee paths (`mint`, `payGaslessBasefee`)
*(consensus, 2 of 6 reports)*
- Location: `contracts/ERC20ControlerMinterUpgradeable.sol` : `mint`; `contracts/Token.sol` : `payGaslessBasefee`
- Mechanism: Blacklist/pause are enforced only on the `transfer*` paths via `transferSanity`. `mint` calls `_mint(to, …)` and `payGaslessBasefee` does `_update(payer, paymaster, _gaslessBasefee)` with no `isBlacklisted` check on the parties.
- Impact: Tokens can be minted to a blacklisted recipient and a blacklisted relayer can still earn gasless basefees — weakens the blacklist guarantee on inbound flows for a compliance-oriented stablecoin. Requires a trusted minter/forwarder; low severity.
- Reviewer disagreement: None.

## Minority findings

## `setMasterMinter` emits an allowance it never writes (event/storage desync)
*(minority, 1 of 6 reports)*
- Location: `contracts/ERC20ControlerMinterUpgradeable.sol` : `setMasterMinter`
- Mechanism: It emits `MinterAllowanceUpdated(newMasterMinter, type(uint256).max)` but never sets `minterAllowed[newMasterMinter]`, so `getMinterAllowance(newMasterMinter)` returns 0 while the event advertises max. (On-chain, `MASTER_MINTER` bypasses the allowance check entirely, so funds aren't at risk.)
- Impact: Off-chain indexers/dashboards record a max allowance that does not exist in storage. Event-vs-storage divergence, no theft.
- Reviewer disagreement: 3 of 6 reports (opus shots 1–3) affirmed the role setters are access-control-sound, but addressed only the access-control axis, not this event/storage divergence.

## Role-rotation setters brick if the role's member set is emptied
*(minority, 1 of 6 reports)*
*(conflicting reviews: 3 of 6 reports defended these setters as access-control-sound)*
- Location: `contracts/ERC20AdminUpgradeable.sol` : `setAdministrator`; `ERC20ControlerMinterUpgradeable.sol` : `setMasterMinter`; `contracts/Token.sol` : `setOwner` (each calls `revokeRole(role, getRoleMember(role, 0))`)
- Mechanism: `AccessControlEnumerable.getRoleMember(role, 0)` reverts on an empty set. An inherited `renounceRole` or external revoke can empty `ADMIN`/`MASTER_MINTER`/`OWNER`; once empty, the rotation function reverts on `getRoleMember(role, 0)` before it can appoint a replacement.
- Impact: Permanent loss of the ability to appoint a new admin/master-minter/owner (liveness brick) if a role ever reaches zero members. Requires a privileged renounce/revoke; low likelihood.
- Reviewer disagreement: Opus shots 1–3 declared `addMinter`/`setMasterMinter`/`setOwner` "correctly gated" and not exploitable — a defense on the access-control axis only; none rebutted the empty-member-set liveness brick.

## `ForwardRequest` has no deadline / expiry — signed requests are executable forever
*(minority, 1 of 6 reports)*
- Location: `contracts/Forwarder.sol` : `ForwardRequest` / `execute`
- Mechanism: `ForwardRequest` has no deadline field, so a valid signed request remains executable indefinitely as long as its per-sender nonce is unused; the relayer alone picks the execution moment.
- Impact: A relayer can hold a stale signed forwarded transfer and submit it at an unfavorable later time (e.g. once the current `_gaslessBasefee` is higher), provided the signer still has sufficient balance.
- Reviewer disagreement: Other forwarder findings flagged the domain-separator replay but none defended (or addressed) the absence of an expiry.

## `burn` skips the blacklist check its own comment claims to perform
*(minority, 1 of 6 reports)*
- Location: `contracts/ERC20ControlerMinterUpgradeable.sol` : `burn`
- Mechanism: The function's comment states it checks the blacklist, but the code performs the burn without an `isBlacklisted` check.
- Impact: A blacklisted minter can still burn their own balance — no attacker gain, but the implementation contradicts its stated compliance behavior.
- Reviewer disagreement: No other report addressed `burn`.

## `transferWithAuthorization` performs an immediate transfer, not an approval, despite EIP-3009-style naming
*(minority, 1 of 6 reports)*
- Location: `contracts/Token.sol` / `ERC20MetaTxUpgradeable.sol` : `transferWithAuthorization`
- Mechanism: The function name follows EIP-3009 conventions that integrators may read as an authorization/approval, but it executes an immediate transfer to `spender`.
- Impact: A frontend/integration foot-gun: callers expecting approval semantics can mis-handle the call. No direct theft.
- Reviewer disagreement: No other report addressed the naming/semantics of this function.

## `setGaslessBasefee` has no upper bound
*(minority, 1 of 6 reports)*
- Location: `contracts/FeesHandlerUpgradeable.sol` : `setGaslessBasefee`
- Mechanism: The setter accepts any `uint256` with no maximum (the `< 0` check on an unsigned value is dead code).
- Impact: A misconfigured or compromised admin can set the gasless basefee arbitrarily high; combined with the unsigned/execution-time fee finding above, relayers/admin can drain far more than a signer anticipated when executing previously-signed meta-txs.
- Reviewer disagreement: Other reports flagged `_gaslessBasefee` being read at execution time but did not separately call out the absence of an upper bound on the setter.

---

*Reconciliation check: 16 distinct findings across the 6 input reports (by code path + root cause) → 17 entries emitted (the unsigned-meta-tx-fee cluster is split into the fee-amount and basefee-recipient facets, both consensus). No input finding dropped; minority entries include every single-report claim, including those whose code path other reports defended.*

