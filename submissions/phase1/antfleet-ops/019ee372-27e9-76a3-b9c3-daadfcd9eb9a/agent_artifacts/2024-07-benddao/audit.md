# Audit: 2024-07-benddao

A close inspection of the `YieldEthStakingEtherfi.sol` and `YieldEthStakingLido.sol` modules reveals a critical logical flaw in the handling of ETH payments in the `repayETH` functions. 

### Defeating `payable` purpose via erroneous token loop and `approve` requirements
- Location: `src/yield/etherfi/YieldEthStakingEtherfi.sol` (and `src/yield/lido/YieldEthStakingLido.sol`) : `repayETH()`
- Mechanism: Both functions accept `msg.value` and deposit it into WETH. However, directly after wrapping the provided ETH, the contract unconditionally transfers the exact amount of WETH completely back to the `msg.sender`. It then calls `super.repay(...)`, which cascades into `_repay()`. `_repay()` independently assesses the debt offset and instructs the `underlyingAsset` (WETH) to `safeTransferFrom(vars.nftOwner, address(this), vars.extraAmount);`.
- Impact: Since the provided ETH is immediately returned to the caller, the subsequent `safeTransferFrom` will attempt to pull the exact funding back from the user's wallet. If the user did not execute an explicit ERC20 `approve` to allow the staking contract to pull their WETH—under the assumption that paying via `msg.value` would be sufficient—the transaction will revert. This strictly breaks the usability of executing ETH-based repayments and effectively mandates an ERC20 approval workflow on WETH, forcing extra gas expenditure and rendering the expected behavior of the `payable` function obsolete.
