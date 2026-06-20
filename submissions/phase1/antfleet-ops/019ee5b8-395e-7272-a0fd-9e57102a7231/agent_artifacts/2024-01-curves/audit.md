# Audit: 2024-01-curves

## Access Control Modifiers Are No-Ops
- Location: `contracts/Security.sol` : `onlyOwner`, `onlyManager`
- Mechanism: Both modifiers evaluate a boolean expression but never require it. `msg.sender == owner;` and `managers[msg.sender] == true;` do nothing, then execution continues. Every function using these modifiers is effectively public.
- Impact: Any attacker can call privileged functions, including changing protocol fees/destinations, setting managers, transferring ownership, changing the ERC20 factory, replacing the fee redistributor, and calling FeeSplitter manager-only accounting functions. This enables fee theft, protocol configuration takeover, and denial of service.

## Anyone Can Replace FeeSplitter’s Curves Source
- Location: `contracts/FeeSplitter.sol` : `setCurves`
- Mechanism: `setCurves` is public and has no access control. The fee splitter trusts `curves` for holder balances and supply when calculating fee entitlements.
- Impact: An attacker can point `FeeSplitter` to a malicious Curves-like contract that reports arbitrary balances and supply, then manipulate `claimFees` / `batchClaiming` accounting to drain ETH held by the fee splitter.

## Fee Accounting Loses Holder Rewards on Balance Changes
- Location: `contracts/FeeSplitter.sol` : `onBalanceChange`
- Mechanism: `onBalanceChange` overwrites `userFeeOffset[account]` with the current cumulative fee index without first crediting fees already earned by the account. In `Curves._transferFees`, this is called during buys and sells before/around balance-changing flows, so a holder’s pending rewards can be erased.
- Impact: Users can permanently lose accrued holder fees when they buy or sell. This is an accounting flaw that allows fee redistribution to underpay legitimate holders and leave funds misallocated in the splitter.

## Transfers Do Not Update FeeSplitter Accounting
- Location: `contracts/Curves.sol` : `_transfer`
- Mechanism: Internal Curves token transfers update `curvesTokenBalance` but never notify `FeeSplitter` for either sender or receiver. FeeSplitter rewards depend on snapshots via `userFeeOffset`, so balances can move without settling accrued fees.
- Impact: Holder-fee accounting becomes incorrect after transfers. Accrued rewards may be claimed by the wrong address, lost, or over/under-accounted depending on transfer timing.

## Reentrancy During Fee Transfers Allows Inconsistent Trading
- Location: `contracts/Curves.sol` : `_transferFees`
- Mechanism: `_transferFees` makes external calls to `firstDestination`, `curvesTokenSubject`, `referralFeeDestination`, and `feeRedistributor` without a reentrancy guard. Buy and sell state is updated before these calls, and recipient contracts can reenter Curves trading functions while the original trade is still executing.
- Impact: A malicious subject/referral/fee contract can execute nested buys or sells against intermediate state, causing unexpected pricing/accounting behavior and potentially griefing trades or manipulating fee distribution paths.

## Unrestricted ERC20 Factory Replacement Can Break or Hijack Withdrawals
- Location: `contracts/Curves.sol` : `setERC20Factory`
- Mechanism: Because `onlyOwner` is ineffective, anyone can replace `curvesERC20Factory`. Later `withdraw` / `mint` calls trust that factory to deploy the external ERC20 wrapper.
- Impact: An attacker can set a malicious or reverting factory, causing future wrapper deployments to fail or deploy malicious wrapper tokens. This can block withdrawals/deposits for curves whose ERC20 wrapper has not yet been minted.

