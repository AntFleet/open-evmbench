# Audit: 2024-07-benddao

# Security Audit Report

## Isolate Self-Liquidation Steals Bidder Funds
- Location: `src/libraries/logic/IsolateLogic.sol` : `executeIsolateLiquidate` / `src/libraries/logic/ValidateLogic.sol` : `validateIsolateLiquidateLoan`
- Mechanism: The isolate liquidation validation never checks that `msgSender != tokenData.owner` (the NFT owner / borrower). Unlike cross liquidation which explicitly requires `msgSender != borrower`, the isolate path has no such guard. After an auction ends, the original borrower can call `isolateLiquidate` on their own position. When `bidAmount >= borrowAmount`, the bidder's escrowed funds are used to repay the borrower's debt, the NFT is transferred back to the borrower (as `msgSender`), and the excess bid (`bidAmount - borrowAmount`) is sent to `tokenData.owner` (also the borrower). The bidder loses their entire bid and receives nothing.
- Impact: Any borrower whose NFT is in the auction state can wait for the auction to end, then liquidate their own position, stealing 100% of the highest bidder's escrowed funds. This makes the entire isolate auction mechanism untrustworthy—bidders would never participate knowing the borrower can front-run them.

## Wrong Interest Index Used for Yield Cap Supply Check
- Location: `src/libraries/logic/YieldLogic.sol` : `executeYieldBorrowERC20`
- Mechanism: The total supply used for the yield cap comparison is computed as `VaultLogic.erc20GetTotalCrossSupply(assetData, groupData.borrowIndex)`, which passes the **group's borrow index** instead of the **asset's supply index**. `erc20GetTotalCrossSupply` does `totalScaledCrossSupply.rayMul(index)`. The borrow index compounds at the borrow rate while the supply index accrues at the supply rate—these diverge significantly over time. This produces an incorrect (inflated or deflated) total supply figure.
- Impact: The asset-level yield cap check `(totalBorrow + amount) <= totalSupply.percentMul(yieldCap)` uses a wrong `totalSupply`. If the borrow index is larger than the supply index (typical, since borrow rate > supply rate), the cap is artificially loosened, allowing yield borrowers to exceed the intended cap and over-borrow against the pool's actual supply. This can lead to bad debt for the protocol.

## Bot Admin Uses Caller's Yield Account Instead of Stake Owner's
- Location: `src/yield/YieldStakingBase.sol` : `_unstake` / `_repay`
- Mechanism: Both `_unstake` and `_repay` resolve the yield account via `yieldAccounts[msg.sender]`. When the `botAdmin` calls these functions on behalf of a user, `msg.sender` is the bot, so `vars.yieldAccout` is the **bot's** yield account (or address(0) if the bot has none). All downstream calculations—`convertToYieldAssets`, `accountYieldShares`, `accountYieldInWithdraws`, `protocolRequestWithdrawal`, `protocolClaimWithdraw`—use this wrong account. The correct account is `sd.yieldAccount` which is stored in the stake data.
- Impact: If the bot admin has a yield account, unstaking/repaying on behalf of a user would compute withdrawal amounts and modify share balances against the wrong account, corrupting accounting for both the bot's and the user's yield shares. If the bot has no yield account, the functions always revert, making the bot-based liquidation/unstake feature completely non-functional.

## Yield Share Accounting Ignores In-Withdrawal Amounts
- Location: `src/yield/YieldStakingBase.sol` : `_unstake` / `getAccountTotalUnstakedYield` / `getAccountYieldBalance`
- Mechanism: When unstaking, `sd.withdrawAmount` is calculated via `convertToYieldAssets(address(vars.yieldAccout), sd.yieldShare)`, which uses `getAccountTotalUnstakedYield(account)` → `eETH.balanceOf(account)` (or `stETH.balanceOf`). The yield shares (`accountYieldShares`) are decremented, but the actual yield tokens remain in the account until `protocolClaimWithdraw` is called during repay. `accountYieldInWithdraws` is incremented to track this, but `getAccountTotalUnstakedYield` never subtracts `accountYieldInWithdraws` from the token balance. This means the remaining shares are backed by more tokens than they represent.
- Impact: A user with multiple staked NFTs sharing one yield account can unstake them sequentially. Each subsequent unstake computes `withdrawAmount` against an inflated total yield (because previously unstaked but unclaimed yield is still in the balance), allowing the user to withdraw more yield than their remaining shares entitle them to—stealing yield from other NFTs' stakes in the same account or from the protocol.

## PriceOracle Missing Time-Based Staleness Check
- Location: `src/PriceOracle.sol` : `getAssetPriceFromChainlink`
- Mechanism: The function checks `updatedAt != 0` and `answeredInRound >= roundId` but never verifies that the price is recent (e.g., `block.timestamp - updatedAt < threshold`). If a Chainlink feed stops updating (but hasn't been explicitly flagged as stale), the contract will continue using the last reported price indefinitely.
- Impact: Stale oracle prices can be used for borrowing, liquidation, and health factor calculations, leading to incorrect collateral valuations. An attacker could borrow against overvalued collateral or avoid liquidation using outdated prices.

## AddressProvider Emits Wrong Event for DelegateRegistryV2
- Location: `src/AddressProvider.sol` : `setDelegateRegistryV2`
- Mechanism: `setDelegateRegistryV2` emits `YieldRegistryUpdated` instead of a dedicated event for the delegate registry change.
- Impact: Off-chain monitoring and event indexing systems will misattribute delegate registry changes as yield registry changes, potentially causing incorrect automated responses to configuration changes. This is a low-severity operational risk.
