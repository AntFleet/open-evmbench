# Audit: 2024-07-benddao

Here is the security audit report for the provided Solidity codebase. Only genuine, high-severity vulnerabilities have been reported.

---

## 1. System-wide Broken WETH unwrapping/wrapping logic leading to token theft/loss & forced reverts
- **Location**: `VaultLogic.sol` : `wrapNativeTokenInWallet` / `unwrapNativeTokenInWallet` and all calling modules (`BVault.sol`, `CrossLending.sol`, `CrossLiquidation.sol`, `IsolateLending.sol`, `IsolateLiquidation.sol`).
- **Mechanism**: The helper function `unwrapNativeTokenInWallet` attempts to transfer WETH from `user` (which is `msgSender`) to the `PoolManager` via `transferFrom`, withdraws native ETH, and triggers `safeTransferNativeToken(user, amount)`. However, during a withdrawal or borrow with native token (WETH/ETH), the core protocol logic first transfers WETH directly to the specified `receiver` (which may be different from the transaction caller `msgSender`). The code then immediately tries to pull that WETH amount back from `msgSender`'s wallet. Similarly, `wrapNativeTokenInWallet` transfers deposited WETH to the `user` via `transferFrom` before pulling it back during `erc20TransferInLiquidity`.
- **Impact**: Any withdraw or borrow where the `receiver` is a third-party address (or a smart contract) will either revert immediately, or—if the borrower has pre-approved the `PoolManager` and holds a WETH balance—unintentionally steal WETH directly from the borrower's private wallet while sending the WETH to the third party. Furthermore, users transacting strictly in native ETH are forced to approve the `PoolManager` to spend their WETH balance, creating unviable UX and failure under standard interaction patterns.

---

## 2. Severe mathematical flaw in `YieldStakingBase` due to global shared `totalDebtShare` across different pools
- **Location**: `YieldStakingBase.sol` : `convertToDebtShares` / `convertToDebtAssets`
- **Mechanism**: The state variable `totalDebtShare` tracking the cumulative debt shares of the yield staking contract is stored globally. However, `getTotalDebt(poolId)` is calculated dynamically per individual `poolId`. When multiple pools exist, the share-to-asset conversion ratio is corrupted because the global `totalDebtShare` accumulates values from all pools, but is divided by the assets of only a single pool when converting. For example, if a user borrows 10 ETH from Pool 1 and another borrows 5 ETH from Pool 2, the Pool 2 borrower gets a heavily inflated share balance. Consequently, when the Pool 1 borrower repays their debt, the corrupted ratios allow them to reclaim their NFT collateral by paying back only a tiny fraction of their actual borrowed debt.
- **Impact**: Borrowers can exploit the system to unlock and withdraw their valuable NFT collateral from the protocol without repaying the majority of their debt, resulting in critical loss of capital for lenders.

---

## 3. Inability to liquidate/unstake unhealthy positions via bot admin due to wrong lookups of `yieldAccounts`
- **Location**: `YieldStakingBase.sol` : `_unstake` / `_repay`
- **Mechanism**: In `_unstake` and `_repay`, the contract fetches the associated yield account using `yieldAccounts[msg.sender]`. While this works when the original borrower acts as `msg.sender`, it fails when the automated bot admin (`botAdmin = msg.sender`) calls these functions to protect the protocol. Because the bot admin does not have a registered yield account of its own, `yieldAccounts[msg.sender]` resolves to `address(0)`. The correct yield account is stored inside the staking data of the specific asset (`sd.yieldAccount`).
- **Impact**: Protocol-critical operations like unstaking or liquidating defaulted yield staking positions will always revert when triggered by the `botAdmin`. Unbacked or unhealthy positions are permanently locked, leading to inevitable bad debt accumulation.

---

## 4. Active delegations in `IDelegateRegistryV2` are not cleared during asset ownership transfers
- **Location**: `LiquidationLogic.sol` / `SupplyLogic.sol` / `IsolateLogic.sol`
- **Mechanism**: When users deposit ERC721 tokens, they can delegate their utility rights to another address via `delegateERC721()`. This creates a delegation on-chain from the `PoolManager` contract (the actual holder) to the delegate. However, when the token's internal owner changes—such as when `supplyAsCollateral = true` is set during a liquidation or during an internal owner swap—the existing delegation from `PoolManager` is never revoked. Because the on-chain holder of the NFT continues to be the `PoolManager` contract, downstream delegate protocols see the delegation as completely valid.
- **Impact**: A previous owner or their delegate can continue to claim valuable rewards, participate in token gates, or cast votes belonging to the NFT even after they have lost ownership due to liquidation or transfer.
