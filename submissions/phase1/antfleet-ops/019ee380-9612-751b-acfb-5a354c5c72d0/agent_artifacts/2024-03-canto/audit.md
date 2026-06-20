# Audit: 2024-03-canto

Below are the genuine security vulnerabilities I found. I focused on the two stateful, externally-reachable contracts (`ASDRouter`, `ASDUSDC`) and the asD vault, since the OFT/adapter wrappers and test contracts contain no custom logic.

## Unauthenticated `lzCompose` — anyone can drive the router and drain residual balances
- Location: `contracts/asd/asdRouter.sol` : `lzCompose`
- Mechanism: A LayerZero compose receiver must verify that `msg.sender` is the LZ endpoint and that `_from` is an OApp it trusts; the canonical `IOAppComposer` implementation gates this with `require(msg.sender == endpoint)`. Here `lzCompose` is a plain `external payable` function with no caller check at all. The only validation is `ASDUSDC(asdUSDC).whitelistedUSDCVersions(_from)`, which merely constrains `_from` to a whitelisted token, not the caller. Every value the function acts on (`amountLD`, `composeFrom`, the entire `composeMsg` payload, and `msg.value`) is decoded directly from the attacker-supplied `_message`/calldata.
- Impact: An attacker calls `lzCompose` directly with `_from` set to any whitelisted USDC-OFT and a crafted 224-byte payload. The router then `approve`s and `deposit`s `amountLD` of that token *from its own balance* into `asdUSDC`, swaps to NOTE, mints ASD and forwards it to an attacker-chosen `_dstReceiver`. Any tokens sitting in the router (residual amounts from prior composes, executor pre-funding, or stray transfers) can be converted to ASD and stolen, and the attacker can also redirect the `_cantoRefundAddress`/`_dstReceiver` of in-flight legitimate composes. This is the standard "spoofed compose" vector and is critical.

## `_refundToken` can revert, breaking the "must never revert" invariant and locking funds
- Location: `contracts/asd/asdRouter.sol` : `_refundToken` (and its callers in `lzCompose` / `_sendASD`)
- Mechanism: The whole design depends on `lzCompose` never reverting (explicitly noted: "Cannot revert anywhere, must send the tokens to the intended receiver if something fails (token's will be lost otherwise)"). Every internal step uses low-level `call` to swallow reverts — except the refund path itself. `_refundToken` calls `IERC20(_tokenAddress).transfer(...)` (raw, return value ignored — fine for revert, but) and, critically, `payable(_refundAddress).transfer(_nativeAmount)`. The native `.transfer` forwards only 2300 gas and reverts if `_refundAddress` is a contract with a non-trivial `receive`/fallback. A token that reverts on transfer (e.g. transfer to a blacklisted address, or a non-standard ERC20) will likewise revert.
- Impact: Because `_refundToken` is the fallback that all failure branches rely on, a revert here propagates out of `lzCompose`. The compose message can no longer be successfully executed, and the underlying tokens delivered to the router are stranded — exactly the loss the contract claims to prevent. A refund recipient that cannot receive native value via 2300 gas permanently bricks that message's settlement.

## `ASDUSDC.withdraw` lets you redeem a different USDC version than you deposited
- Location: `contracts/asd/asdUSDC.sol` : `withdraw` / `deposit`
- Mechanism: `asdUSDC` is fungible across all whitelisted versions — `deposit` mints generic `asdUSDC` and `withdraw` burns generic `asdUSDC`, but the caller freely chooses `_usdcVersion` on withdrawal, constrained only by that version's `usdcBalances` bookkeeping. There is no link between the version a user deposited and the version they may withdraw. The contract treats every whitelisted version as exactly 1:1 with every other.
- Impact: If any whitelisted USDC version depegs, is compromised, or is simply less desirable, an attacker can deposit the bad version (minting `asdUSDC`) and withdraw the good version, draining the contract's holdings of the healthy token at par. Even absent a depeg this collapses all versions to a single redemption queue, so holders of the "worst" version can socialize losses onto everyone by exiting through the best version.

## `ASDUSDC` decimal scaling reverts/over-mints for versions with ≠ default decimals
- Location: `contracts/asd/asdUSDC.sol` : `deposit` / `withdraw`
- Mechanism: Both functions compute `10 ** (this.decimals() - ERC20(_usdcVersion).decimals())`. `asdUSDC` uses the default 18 decimals. If a whitelisted version has *more* than 18 decimals, the `uint8` subtraction underflows and the call reverts (DoS for that version). The `withdraw` side uses integer division `_amount / 10**(...)`, which truncates: redeeming amounts that don't divide evenly silently rounds the user's payout down while the difference stays locked in the contract.
- Impact: Mis-decimaled whitelisting permanently DoSes deposits/withdrawals for that version; the truncating division in `withdraw` causes systematic dust loss to users in favor of the contract.

## Cross-chain swap never approves CrocSwap, so the swap branch always fails on a real DEX
- Location: `contracts/asd/asdRouter.sol` : `_swapOFTForNote` (called from `lzCompose`)
- Mechanism: For the deposit step the router explicitly `approve`s `asdUSDC`, and for the vault step it `approve`s the ASD vault, but before invoking `ICrocSwapDex.swap` it never grants `crocSwapAddress` an allowance over the input `asdUSDC` and passes `reserveFlags = 0` (direct token settlement, i.e. CrocSwap will `transferFrom` the router). The `MockCrocSwapDex` hides this because it *sends* tokens to the caller instead of pulling them, so tests pass.
- Impact: Against the real Ambient/CrocSwap dex the swap reverts for lack of allowance, is caught by the `call`, and the flow takes the "swap failed" branch — refunding `asdUSDC` on Canto. Every cross-chain deposit that should have produced ASD instead silently delivers wrapped USDC to the Canto refund address, i.e. the core function is non-operational and silently mis-settles user funds.

## `withdrawCarry` static-calls a non-view `balanceOfUnderlying`
- Location: `contracts/asd/asdOFT.sol` : `withdrawCarry`; interface `contracts/clm/CTokenInterfaces.sol` : `CTokenInterface.balanceOfUnderlying`
- Mechanism: The interface declares `balanceOfUnderlying` as `view`, so Solidity compiles the call as a `STATICCALL`. In Compound v2 (and cNOTE), `balanceOfUnderlying` is state-mutating (it accrues interest via `exchangeRateCurrent`). A state-writing function invoked under `STATICCALL` reverts.
- Impact: If cNOTE follows the standard Compound semantics, `withdrawCarry` reverts unconditionally, permanently locking all accrued interest ("carry") in the contract. (Confidence depends on Canto's exact cNOTE implementation — some forks expose a `view` variant — but the `view` annotation on a function that accrues interest is a latent correctness/funds-lock bug.)

## Excess `msg.value` is not refunded in the cross-chain send path
- Location: `contracts/asd/asdRouter.sol` : `_sendASD`
- Mechanism: In the non-Canto branch the router forwards exactly `_payload._feeForSend` to the OFT `send` call. Any `msg.value` in excess of `_feeForSend` (and all `msg.value` in the Canto branch) is neither used nor returned. There is no sweep of leftover native balance.
- Impact: Native value delivered with the compose beyond the exact LZ fee accumulates and is stranded in the router. Combined with the missing access control above, this is minor, but it is a real value leak in the intended executor flow.

The OFT/OFTAdapter wrappers, `Turnstile`, and the `test-contracts/*` files contain no custom security-relevant logic.

