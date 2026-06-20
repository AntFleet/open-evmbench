# Audit: 2024-01-curves

 ## 1. Non-functional access-control modifiers
- Location: `contracts/Security.sol` : `onlyOwner()`, `onlyManager()` (inherited by `Curves` and `FeeSplitter`)
- Mechanism: Both modifiers write the access check as a bare boolean expression — `msg.sender == owner;` and `managers[msg.sender] == true;` — without `require(...)`, `if (...){...}`, or a return. Solidity evaluates the expression, discards the result, and proceeds with the function body, so the check never reverts.
- Impact: Every privileged function is callable by any address. In `Curves` this includes `setProtocolFeePercent`, `setExternalFeePercent`, `setMaxFeePercent`, `setERC20Factory`, `setFeeRedistributor`, `transferOwnership`, and `setManager`; in `FeeSplitter` it includes `addFees`, `onBalanceChange`, `transferOwnership`, and `setManager`. An attacker can redirect all fee destinations to themselves, raise fees to 100%, replace the ERC-20 factory with a malicious one, or take over owner/manager roles and fully compromise the protocol.

## 2. `FeeSplitter.setCurves` has no access control
- Location: `contracts/FeeSplitter.sol` : `setCurves(Curves curves_)`
- Mechanism: The function is public and has no access-control modifier; it directly overwrites the `curves` state variable used by `balanceOf`, `totalSupply`, `addFees`, and every fee calculation.
- Impact: Anyone can point `FeeSplitter.curves` at a malicious contract that returns arbitrary balances and supplies, then call `claimFees`/`batchClaiming` to drain all ETH held by the fee splitter.

## 3. Holder-fee accounting is not updated on transfers, withdrawals, or deposits
- Location: `contracts/Curves.sol` : `_transfer()` (used by `transferCurvesToken()`, `transferAllCurvesTokens()`, `withdraw()`, `deposit()`)
- Mechanism: `FeeSplitter.onBalanceChange(token, account)` — which resets a holder's `userFeeOffset` to the current `cumulativeFeePerToken` — is only invoked inside `_transferFees()` during buys and sells. Gifting, migrating, wrapping, or unwrapping tokens calls `_transfer()` but never touches the fee accounting.
- Impact: A recipient whose `userFeeOffset` is stale (for example, a fresh address receiving its first tokens) can call `FeeSplitter.claimFees()` and receive `(cumulativeFeePerToken - userFeeOffset) * balance`, effectively claiming the entire historical holder-fee pool for that subject and stealing rewards from legitimate long-term holders.

## 4. Excess ETH paid during buys is not refunded
- Location: `contracts/Curves.sol` : `_buyCurvesToken()` (called by `buyCurvesToken()`, `buyCurvesTokenWithName()`, `buyCurvesTokenForPresale()`, `buyCurvesTokenWhitelisted()`)
- Mechanism: The function validates `msg.value >= price + totalFee` but never sends back the surplus; any ETH above the exact required amount simply remains in the `Curves` contract.
- Impact: Buyers permanently lose any overpayment, whether from a slippage buffer, a front-end pricing error, or a user sending more than the computed `getBuyPriceAfterFee`.

## 5. Reverting ETH recipients can DoS all trading of a curve
- Location: `contracts/Curves.sol` : `_transferFees()`
- Mechanism: On every trade the contract sends the subject fee with `curvesTokenSubject.call{value: subjectFee}("")` and, when configured, the referral fee with `referralFeeDestination[curvesTokenSubject].call{value: referralFee}("")`. If either destination is a smart contract that lacks a payable `receive()/fallback()` or one that deliberately reverts, the `.call` returns `success=false` and `_transferFees()` reverts with `CannotSendFunds()`.
- Impact: A token subject can deploy a non-receiving contract as the curves-token subject, or set a rejecting referral address via `setReferralFeeDestination()`, and freeze all buys and sells for their curve. Combined with finding 1, a compromised protocol fee destination can also freeze global trading.

## 6. Wrapping the entire unwrapped supply halts the market
- Location: `contracts/FeeSplitter.sol` : `addFees()` (reachable from `Curves._transferFees()`)
- Mechanism: `FeeSplitter.totalSupply(token)` returns `curves.curvesTokenSupply(token) - curves.curvesTokenBalance(token, address(curves))`. When every holder calls `Curves.withdraw()`, all unwrapped curve tokens move into the `Curves` contract and `totalSupply_` becomes zero, causing `addFees()` to revert with `NoTokenHolders`.
- Impact: Because `_transferFees()` unconditionally calls `feeRedistributor.addFees{value: holderFee}()` whenever `holdersFeePercent > 0` and a fee splitter is set, a holder of the whole unwrapped supply can withdraw everything into the ERC-20 wrapper and cause every subsequent buy/sell of that subject to revert, effectively killing the market.

## 7. Fee claims use gas-limited `transfer`
- Location: `contracts/FeeSplitter.sol` : `claimFees()`, `batchClaiming()`
- Mechanism: Both payout paths use `payable(msg.sender).transfer(claimable)`, which forwards only 2300 gas to the recipient.
- Impact: Smart-contract accounts such as multisigs, Gnosis Safes, or smart wallets whose `receive()`/`fallback()` requires more than 2300 gas cannot successfully claim fees; the `transfer` reverts and their rewards become inaccessible.

## 8. One-block dead zone between presale and public sale
- Location: `contracts/Curves.sol` : `buyCurvesToken()` and `buyCurvesTokenWhitelisted()`
- Mechanism: Public buy reverts when `startTime != 0 && startTime >= block.timestamp`; whitelisted buy reverts when `startTime == 0 || startTime <= block.timestamp`. At the exact block where `block.timestamp == startTime`, both conditions are true and both functions revert.
- Impact: No trade can be executed for that subject during the scheduled transition block.

## 9. `transferAllCurvesTokens` is griefable via unbounded owned-subjects array
- Location: `contracts/Curves.sol` : `_addOwnedCurvesTokenSubject()` / `transferAllCurvesTokens()`
- Mechanism: `_transfer()` appends a subject to `ownedCurvesTokenSubjects[owner]` for each distinct token ever received, but never removes entries when the balance later becomes zero. `transferAllCurvesTokens()` iterates the entire array, and `_addOwnedCurvesTokenSubject()` performs a linear duplicate check on each iteration.
- Impact: An attacker can send dust amounts of many different curve subjects to a victim, causing the array to grow until the victim’s `transferAllCurvesTokens()` call exceeds the block gas limit and reverts, permanently disabling the bulk-migration function for that address.
