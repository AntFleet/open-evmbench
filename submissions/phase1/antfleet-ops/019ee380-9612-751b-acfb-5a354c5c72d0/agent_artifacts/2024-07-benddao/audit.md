# Audit: 2024-07-benddao

I'll report the genuine security vulnerabilities I found. The most serious is an accounting error in isolate-loan liquidation.

## Isolate liquidation over-debits the bid escrow (`totalBidAmout` underflow / escrow drain)
- Location: `src/libraries/logic/IsolateLogic.sol` : `executeIsolateLiquidate` (interacting with `VaultLogic.erc20TransferOutBidAmountToLiqudity`)
- Mechanism: At liquidation, the only funds actually sitting in the bid escrow for the loan are the last bid (`loanData.bidAmount`). When the accrued debt has grown above that bid, the code computes `vars.extraBorrowAmounts[i] = borrowAmount - bidAmount` and requires the liquidator to top up `totalExtraAmount` separately via `erc20TransferInLiquidity`. However, it then reclassifies escrow→liquidity by calling `erc20TransferOutBidAmountToLiqudity(debtAssetData, vars.totalBorrowAmount)`, which does `assetData.totalBidAmout -= totalBorrowAmount`. Since `totalBorrowAmount = (escrowed bids) + totalExtraAmount`, the bid-escrow counter is debited by `totalExtraAmount` more than the bids that were ever escrowed. The correct amount to move is the escrowed bid portion (`totalBorrowAmount - totalExtraAmount`). 
- Impact: For a lone underwater loan (the normal case, because interest accrues between the final bid and the end of the auction window, so `borrowAmount > bidAmount`), `totalBidAmout -= totalBorrowAmount` underflows and reverts — isolate liquidation becomes impossible, permanently locking the collateral NFT and leaving the bad debt unrecoverable (DoS / frozen funds). When other auctions for the same debt asset have bids escrowed (so no underflow), the `totalExtraAmount` is silently siphoned out of those other bidders' escrow into `availableLiquidity`; suppliers can then withdraw funds that are owed to those bidders as refunds, leaving the protocol insolvent against pending bid refunds.

## Chainlink price feed has no staleness or bounds validation
- Location: `src/PriceOracle.sol` : `getAssetPriceFromChainlink`
- Mechanism: The function reads `latestRoundData()` and only enforces `answer > 0`, `updatedAt != 0`, and `answeredInRound >= roundId`. There is no check that `updatedAt` is recent (no per-feed heartbeat/staleness tolerance) and no min/max sanity bound. `updatedAt != 0` is effectively always true and does not detect a frozen/stale feed; `answeredInRound >= roundId` is the deprecated round-completeness check and does not bound age either. This price feeds directly into collateral/debt valuation (`GenericLogic`, `LiquidationLogic`) and into the NFT-oracle base-currency conversion (`getAssetPriceFromBendNFTOracle`).
- Impact: If an aggregator stops updating (operator outage, deprecated feed, L2 sequencer issue), the protocol keeps using the last reported value indefinitely. Borrowers can borrow against collateral whose true value has dropped, or healthy users can be wrongly liquidated, on a price that no longer reflects the market — leading to bad debt or unjust liquidations.

---

I also checked the dispatcher/proxy trailing-parameter packing (`PoolManager.dispatch`/`Proxy`/`BaseModule.unpackTrailingParams`), the cross-liquidation close-factor and collateral-bonus math, the scaled supply/borrow accounting in `VaultLogic`, and the access-control wiring (`ACLManager`/`onlyPoolAdmin`/`onlyOracleAdmin`). These are consistent. One non-security note that is *not* a vulnerability: `AddressProvider.setDelegateRegistryV2` emits `YieldRegistryUpdated` instead of a delegate-registry event — cosmetic only, so I'm not counting it as a finding.

