# Audit: 2024-06-thorchain

 ## Public `swapOutV5` can drain ERC20 tokens held by the aggregator
- Location: `chain/ethereum/contracts/THORChain_Aggregator.sol` : `swapOutV5`
- Mechanism: In the `fromAsset != address(0)` branch the function approves `swapRouter` for `fromAmount` and calls `swapExactTokensForETH` using tokens already in the aggregator contract. It is `public`, has no `onlyOwner` check, and never verifies that the caller is the THORChain router or that the caller transferred the tokens.
- Impact: Anyone can swap any ERC20 tokens that are stuck in the aggregator (fee leftovers, refunds, donations, etc.) to ETH and receive them at an attacker-controlled `recipient`.

## Router V5 native fallback sends ETH to the aggregator instead of the recipient
- Location: `chain/ethereum/contracts/THORChain_Router.sol` : `_transferOutAndCallV5`
- Mechanism: When `fromAsset == address(0)` and the aggregator’s `swapOutV5` fails, the fallback is `payable(aggregationPayload.target).send(msg.value)` rather than sending to `aggregationPayload.recipient`; the `TransferOutAndCallV5` event still records the recipient.
- Impact: If an aggregator swap fails, the user’s native output is sent to the aggregator contract instead of the intended recipient. A malicious aggregator can deliberately revert `swapOutV5` to steal the ETH.

## `batchTransferOutAndCallV5` reuses the full `msg.value` for every native item
- Location: `chain/ethereum/contracts/THORChain_Router.sol` : `batchTransferOutAndCallV5` → `_transferOutAndCallV5`
- Mechanism: For each native (`fromAsset == address(0)`) payload, `_transferOutAndCallV5` forwards `msg.value` to the target, instead of the per-item `fromAmount`. The function never checks that the sum of native amounts equals `msg.value`.
- Impact: A batch containing more than one native transfer will either revert after the first item consumes all attached ETH or overpay the first aggregator/target, making native batch transfers effectively broken.

## `swapIn` leaves non-zero token allowances for fee-on-transfer tokens, blocking future swaps
- Locations: `chain/ethereum/contracts/THORChain_Aggregator.sol` : `swapIn` → `safeApprove`; `avalanche/src/contracts/AvaxAggregator.sol` : `swapIn`; `chain/avalanche/src/contracts/AvaxAggregator.sol` : `swapIn`
- Mechanism: `swapIn` pulls `safeAmount` (which is less than `amount` for fee-on-transfer tokens) but approves the DEX router for the full `amount`. After the swap, the allowance remains `amount - safeAmount > 0`. The Ethereum aggregator’s custom `safeApprove` does not reset the allowance to zero first, and the Avalanche aggregator’s OpenZeppelin `SafeERC20.safeApprove` explicitly reverts on a non-zero-to-non-zero allowance change.
- Impact: Once a fee-on-transfer token such as USDT is used, the aggregator can no longer approve that token for later swaps, permanently DoSing the token route.

## `_routerDeposit` does not reset allowance and ignores the approve return value
- Locations: `chain/ethereum/contracts/THORChain_Router.sol` : `_routerDeposit` → `safeApprove`; `avalanche/src/contracts/AvaxRouter.sol` : `_routerDeposit`; `chain/avalanche/src/contracts/AvaxRouter.sol` : `_routerDeposit`
- Mechanism: `_routerDeposit` approves the destination router for the full `_amount` in a single low-level call and only checks call success, not the boolean return value. It never sets the allowance to zero before re-approving. For tokens like USDT that require a zero allowance before a non-zero approval, any leftover approval (e.g., from a fee-on-transfer token where the destination router receives less than `_amount`) makes the approval revert.
- Impact: Router migrations and allowance transfers can be permanently blocked for USDT and similar tokens, and silently-failing approvals are not detected.

## `ETH_RUNE.transferTo` uses `tx.origin` and can drain users
- Location: `chain/ethereum/contracts/eth_rune.sol` : `transferTo`
- Mechanism: `transferTo(recipient, amount)` calls `_transfer(tx.origin, recipient, amount)` without an allowance check and without verifying that `msg.sender` is the token owner.
- Impact: A phishing contract can call `ETH_RUNE.transferTo(attacker, balanceOf[user])` while the user is the transaction origin, draining the user’s RUNE balance.

## `TransferOut` events are emitted for failed native transfers
- Locations: `chain/ethereum/contracts/THORChain_Router.sol` : `transferOut`, `_transferOutV5`, `_transferOutAndCallV5`; `avalanche/src/contracts/AvaxRouter.sol` : `transferOut`, `transferOutAndCall`; `chain/avalanche/src/contracts/AvaxRouter.sol` : `transferOut`, `transferOutAndCall`
- Mechanism: When an ETH/AVAX send fails (recipient or aggregator reverts, or `.send` returns false), the contract bounces the funds back to the vault/sender but still emits `TransferOut`/`TransferOutAndCallV5` with the original amount and the intended recipient/target.
- Impact: Off-chain observers that rely on event logs can be tricked into recording a successful outbound transfer that never reached the recipient, leading to incorrect cross-chain accounting.

## `swapIn` deposits the entire contract ETH/AVAX balance instead of the swap output
- Locations: `chain/ethereum/contracts/THORChain_Aggregator.sol` : `swapIn`; `avalanche/src/contracts/AvaxAggregator.sol` : `swapIn`; `chain/avalanche/src/contracts/AvaxAggregator.sol` : `swapIn`
- Mechanism: After the DEX swap the function sets the deposit amount to `address(this).balance` and deposits the full balance via `depositWithExpiry`, rather than tracking only the ETH/AVAX produced by the swap.
- Impact: Any ETH/AVAX already held by the aggregator (donations, refunds, or previously stuck funds) is swept into the THORChain vault, so the amount recorded in the memo can differ from the actual swap output and funds can be lost.

## `rescueFunds` gives the owner unilateral withdrawal rights over all assets
- Location: `chain/ethereum/contracts/THORChain_Aggregator.sol` : `rescueFunds`
- Mechanism: The `onlyOwner` function can transfer any amount of any ERC20 or ETH out of the aggregator to an arbitrary destination, and there is no function to renounce or transfer ownership safely.
- Impact: If the owner key is compromised, all funds that ever become stuck in the aggregator can be stolen.
