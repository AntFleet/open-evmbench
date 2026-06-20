# Audit: 2024-07-benddao

## Anyone can seize an isolated-loan auction NFT
- Location: `src/libraries/logic/IsolateLogic.sol` : `executeIsolateLiquidate`
- Mechanism: After an isolated auction ends, liquidation transfers the NFT to `params.msgSender` instead of `loanData.lastBidder`, and there is no check that the caller is the winning bidder. The winning bid escrow is still used to repay the loan, but the collateral recipient is whichever address calls `isolateLiquidate`.
- Impact: Any attacker can wait for an auction to end, call `isolateLiquidate`, and receive the NFT while the real winner’s escrowed bid pays the debt. If accrued debt exceeds the bid, the attacker only pays the small extra amount.

## Isolated-loan repay and redeem burn debt from the wrong account
- Location: `src/libraries/logic/IsolateLogic.sol` : `executeIsolateRepay`, `executeIsolateRedeem`
- Mechanism: Isolated loans are tied to the NFT owner when borrowed, but repay/redeem do not verify that `params.onBehalf` or `params.msgSender` is the NFT owner. They reduce `groupData.userScaledIsolateBorrow[params.onBehalf]` or `[params.msgSender]` while reducing `loanData.scaledAmount` for the target NFT. A third party with debt in the same group can therefore apply their repayment to someone else’s loan record.
- Impact: Attackers can corrupt isolated-loan accounting, reset auctions, unlock or alter another user’s loan, and leave ghost debt or loan records that no longer match per-user debt. This can make affected isolated positions unrepayable or unliquidatable.

## Group-specific borrow constraints can be bypassed after borrowing
- Location: `src/libraries/logic/SupplyLogic.sol` : `executeWithdrawERC20`, `executeWithdrawERC721`, `executeSetERC721SupplyMode`
- Mechanism: Cross-borrow validation enforces collateral and LTV per `classGroup`, but withdrawals and supply-mode changes only call aggregate `validateHealthFactor`. A borrower can borrow against collateral in group A, add collateral in group B, then withdraw or move group A collateral as long as the global health factor remains healthy.
- Impact: Debt can remain outstanding in a group with no valid group collateral, bypassing intended risk segregation and group-level LTV limits. Positions may be non-liquidatable while violating the group constraints that were required at borrow time.

## Yield borrow caps are calculated with the borrow index instead of the supply index
- Location: `src/libraries/logic/YieldLogic.sol` : `executeYieldBorrowERC20`
- Mechanism: The yield-cap checks compute `vars.totalSupply` using `VaultLogic.erc20GetTotalCrossSupply(assetData, groupData.borrowIndex)`. That function expects the asset supply index, not the group borrow index. As borrow interest accrues, the borrow index can exceed the supply index and overstate available supply for cap calculations.
- Impact: Whitelisted yield managers can borrow beyond the configured asset-level and manager-level yield caps, increasing undercollateralized exposure beyond governance limits.

## Chainlink prices never expire
- Location: `src/PriceOracle.sol` : `getAssetPriceFromChainlink`
- Mechanism: The oracle only checks `answer > 0`, `updatedAt != 0`, and `answeredInRound >= roundId`. It does not enforce a maximum staleness window for `updatedAt`. A feed that has stopped updating but still returns an old positive answer is accepted indefinitely.
- Impact: Borrowing, liquidation, and health-factor checks can use obsolete prices, allowing users to borrow too much, avoid liquidation, or be incorrectly liquidated after market prices move.

## ERC721 delegations persist across internal ownership changes
- Location: `src/libraries/logic/PoolLogic.sol` : `executeDelegateERC721`
- Mechanism: Delegations are written to Delegate Registry from the pool contract address for a specific NFT token, but withdrawals, liquidations, and internal ownership transfers do not revoke delegations. Since the delegation is keyed to the pool as `from`, not the protocol’s internal owner, an old depositor’s delegate can remain authorized when the same token is later held in the pool for a different owner.
- Impact: A previous owner’s delegate can retain rights over an NFT while it is deposited by a later owner, allowing unauthorized use of external delegation-gated rights such as claims, game actions, or other NFT-linked benefits.

