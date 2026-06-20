# Audit: 2024-06-thorchain

Here is the security audit report for the provided codebase.

## 1. Complete User Fund Theft via `tx.origin` Authorization
- **Location:** `ethereum/contracts/eth_rune.sol` : `transferTo`
- **Mechanism:** The `transferTo` function is completely missing access controls and uses `tx.origin` instead of `msg.sender` for the `from` parameter in the underlying `_transfer` call. Any caller can trigger this function and target unrestricted EOAs. If a victim can be tricked into interacting with a malicious contract (which in turn calls this function), the attacker’s contract can initiate an approval-less sweep of the victim's entire `ETH_RUNE` balance.
- **Impact:** Attackers can trivially drain ETH.RUNE from victims via standard phishing interactions, completely bypassing the ERC-20 approval schema.

## 2. Unrestricted Native ETH Drainage in V5 Transfer
- **Location:** `ethereum/contracts/THORChain_Router.sol` : `_transferOutV5`
- **Mechanism:** The internal helper `_transferOutV5` handles native ETH disbursements (when `asset == address(0)`). Unlike the V4 predecessor `transferOut` which strictly bound the outbound transfer to `msg.value` (i.e. `safeAmount = msg.value`), the V5 function arbitrarily trusts the user-supplied struct parameter (`transferOutPayload.amount`). Because `transferOutV5` and `batchTransferOutV5` are freely callable `public`/`external` functions lacking access control, any caller can submit a payload with `asset = address(0)` and an arbitrary `amount`. 
- **Impact:** An attacker can provide a `msg.value` of 0 and request a massive `transferOutPayload.amount`, directing any accumulated or stuck Native ETH in the router directly to themselves.

## 3. Permanent DoS of Swaps for Fee-On-Transfer Tokens 
- **Location:** `avalanche/src/contracts/AvaxAggregator.sol` : `swapIn`
- **Mechanism:** The `swapIn` function accepts ERC20 tokens and approves them to the `swapRouter` utilizing OpenZeppelin's `SafeERC20` module. The function takes the user-supplied `amount`, tracks the underlying actual received magnitude as `safeAmount`. It then triggers `IERC20(...).safeApprove(..., amount)` before asking the swap router to pull `safeAmount`. If a token tracks a transfer fee (or deflation mechanisms), `safeAmount` will be strictly less than `amount`. The router will pull `safeAmount`, leaving an active residual non-zero allowance of `amount - safeAmount` to the router. OpenZeppelin's `safeApprove` contains a strict require-check preventing the approval of a non-zero value when the current allowance is already non-zero.
- **Impact:** If a fee-on-transfer token is routed, the first transaction will leave a residual allowance. Subsequent users attempting to trade that exact token will trigger an immediate revert, permanently locking the operational routing path for that token sequence.

## 4. Aggregator Residual Balance Extractor
- **Location:** `ethereum/contracts/THORChain_Aggregator.sol` and `avalanche/src/contracts/AvaxAggregator.sol` : `swapIn`
- **Mechanism:** In the final sequence of the `swapIn` function, the codebase resolves the resulting destination swap assets by querying `_safeAmount = address(this).balance` and subsequently forwards the entirety of the contract's Native Asset (ETH/AVAX) balance into the router with the user's memo. There is no scoping to just the expected swap outcome amount. 
- **Impact:** If Native assets accumulate inside the Aggregator for any reason (direct transfer, previous slippage anomalies, failed external calls), an attacker can call `swapIn` with a fractional negligible `amount` (e.g., 1 wei) of an arbitrary token pointing to their own Thorchain wallet memo context. The resulting native transfer sweeps all locked funds inside the Aggregator to the attacker's personal destination.

## 5. Loop Collisions via `msg.value` Re-Use 
- **Location:** `ethereum/contracts/THORChain_Router.sol` : `batchTransferOutAndCallV5`
- **Mechanism:** The external `batchTransferOutAndCallV5` iterates an array of payloads calling the internal `_transferOutAndCallV5`. When `fromAsset == address(0)`, the function relays external actions delegating dynamic values to the target `call{value: msg.value}`. Because `msg.value` acts as a static shared environment variable evaluated from the initial transaction trigger, if a user passes multiple ETH payloads within the single array, the first iteration passes successfully and depletes the message value, but subsequent iterations will revert as they try to force the single original `msg.value` again without reserving explicit limits. Lookbacks from failed swaps default entirely to trying to fallback `payable(msg.sender).transfer(msg.value)`, invoking a hard crash. 
- **Impact:** Attempting to batch multiple native ether aggregator calls will revert due to exhausted contract balances. Users (or automated consensus vaults) employing the batch design for parallel ETH aggregations will involuntarily suffer a denial of service on perfectly legitimate transactions.
