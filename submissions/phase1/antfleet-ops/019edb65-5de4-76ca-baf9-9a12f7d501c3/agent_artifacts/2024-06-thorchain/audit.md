# Audit: 2024-06-thorchain

## Incorrect fallback recipient in native asset swap failure
- Location: `chain/ethereum/contracts/THORChain_Router.sol` : `_transferOutAndCallV5`
- Mechanism: When `fromAsset == address(0)` (native ETH/AVAX) and the call to the aggregator’s `swapOutV5` fails, the code attempts a fallback to send the native asset directly. The intended recipient is `aggregationPayload.recipient`, but the code sends `msg.value` to `aggregationPayload.target` (the aggregator itself) instead.
- Impact: If the swap fails (e.g., due to slippage), the user’s native asset is sent to the aggregator contract, which may not have a withdrawal function. The funds are permanently lost; the fallback logic is completely misdirected.

## ERC20 tokens permanently locked when aggregator swap fails
- Location: `chain/ethereum/contracts/THORChain_Router.sol` : `_transferOutAndCallV5`
- Mechanism: For ERC20 assets (`fromAsset != address(0)`), the router first transfers tokens to the aggregator and then calls the aggregator’s `swapOutV5`. If the aggregator’s swap reverts or fails, the router does not revert and makes no attempt to recover the tokens. The vault’s allowance has already been reduced, and the tokens remain in the aggregator contract.
- Impact: A vault can permanently lose the entire transferred amount if the aggregator’s swap fails for any reason (e.g., slippage, stale deadline, or a bug in the aggregator). There is no recovery mechanism.

## Fee‑on‑transfer token accounting mismatch in `transferOut` and `_transferOutAndCallV5`
- Location: `chain/ethereum/contracts/THORChain_Router.sol` : `transferOut` (ERC20 branch) and `_transferOutAndCallV5`
- Mechanism: The router reduces `_vaultAllowance[msg.sender][asset]` by the full `amount` (or `fromAmount`) and then calls `transfer()` on the token. If the token charges a transfer fee, the actual amount transferred is less than the deduction. The router does not measure the actual received amount.
- Impact: Over time, the sum of allowances becomes larger than the router’s actual token balance, leading to under‑collateralisation. Vaults can withdraw more tokens than they should, and later withdrawals may fail due to insufficient balance.

## Fee‑on‑transfer tokens cause swap failure in aggregator `swapOutV5`
- Location: `chain/ethereum/contracts/THORChain_Aggregator.sol` : `swapOutV5`
- Mechanism: The aggregator receives `fromAmount` as a parameter and uses it for the swap. However, if the token has a transfer fee, the actual amount received by the aggregator is less than `fromAmount`. The aggregator does not inspect its balance, approves `fromAmount` to the swap router, and the swap router tries to pull `fromAmount`, which fails because the aggregator’s balance is insufficient.
- Impact: Any swap involving a fee‑on‑transfer token will revert, causing the tokens to be stuck in the aggregator (see previous finding). This effectively disables swaps for such tokens and can lead to permanent loss.
