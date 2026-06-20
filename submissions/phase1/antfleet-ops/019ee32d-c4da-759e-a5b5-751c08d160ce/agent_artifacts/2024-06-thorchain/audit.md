# Audit: 2024-06-thorchain

Below is the security audit report for the provided smart contracts.

## Reentrancy/Phishing Draining in `transferTo` via `tx.origin`
- Location: `chain/ethereum/contracts/eth_rune.sol` : `transferTo`
- Mechanism: The function `transferTo` uses `tx.origin` instead of `msg.sender` as the source of the token transfer: `_transfer(tx.origin, recipient, amount);`. This allows a transfer of the token to be initiated without approval or signature verification as long as the owner of the tokens initiates the top-level transaction. If a user holding `ETH_RUNE` interacts with any malicious external link or contract, that contract can execute a nested call to `transferTo` targeting their balance.
- Impact: Any malicious contract or phishing attack can completely drain the victim's entire `ETH_RUNE` balance upon any interaction.

## Native Asset Misrouting in `batchTransferOutAndCallV5`
- Location: `chain/ethereum/contracts/THORChain_Router.sol` : `_transferOutAndCallV5`
- Mechanism: When transferring out and calling with native ETH (`fromAsset == address(0)`), the contract forwards `msg.value` to the swap aggregator target rather than forwarding the structured payload amount `fromAmount` or a proportional value: `aggregationPayload.target.call{value: msg.value}(...)`. During a batch operation via `batchTransferOutAndCallV5`, the overall transaction contains the sum of multiple swap values as `msg.value`. On the first iteration of the loop, the entire `msg.value` balance of the transaction is sent to the first aggregator target.
- Impact: In batch native swaps, the first swap consumes the total Ether sent for all batches, leading to either immediate failure on the second swap (revert due to insufficient balance) or unintentional loss of excess Ether to the first aggregator.

## Erroneous Fallback Destination on Failed ETH Swaps
- Location: `chain/ethereum/contracts/THORChain_Router.sol` : `_transferOutAndCallV5`
- Mechanism: In the event of a failed native ETH swap (`!swapOutSuccess`), the router implements a fallback mechanism that is designed to return the originally provided ETH to the final user recipient. However, the code incorrectly directs the fallback payment to the aggregator target contract instead of `recipient`: `bool sendSuccess = payable(aggregationPayload.target).send(msg.value);`.
- Impact: If an ETH swap fails on the aggregator side, user funds are incorrectly routed directly to the aggregator contract itself, leading to irreversible loss of assets.

## Silent Loss of ERC20 Funds on Failed Swaps
- Location: `chain/ethereum/contracts/THORChain_Router.sol` : `_transferOutAndCallV5`
- Mechanism: When routing swap actions using an ERC20 asset, the router transfers the token to the target aggregator before invoking the `swapOutV5` function on the target contract. If this swap call fails and returns `false`, the return value `_dexAggSuccess` is captured but ignored without reverting or triggering any ERC20 fallback refund code.
- Impact: The router reports a successful cross-chain operation, but the underlying ERC20 tokens remain stuck inside the aggregator contract on any failed intermediate swap, leading to a silent and permanent loss of user funds.

## Denial of Service via USDT non-standard `approve` Behavior
- Location: `chain/ethereum/contracts/THORChain_Router.sol` : `_routerDeposit` (and `chain/avalanche/src/contracts/AvaxRouter.sol` : `_routerDeposit`)
- Mechanism: Non-standard ERC20 tokens like USDT revert when approving an address that has an already existing non-zero allowance. In the internal function `_routerDeposit`, the router executes `safeApprove(_asset, _router, _amount)` to grant allowance to the next router. Because it does not reset the allowance to `0` first, any subsequent operations transferring allowances for USDT to target routers will revert.
- Impact: Complete denial of service (DoS) for transferring, returning, or churning USDT allowances across routers.

## Permanently Trapped Stuck Assets
- Location: `chain/ethereum/contracts/THORChain_Router.sol` : `transferOut` and `_transferOutV5` (and `chain/avalanche/src/contracts/AvaxRouter.sol` : `transferOut`)
- Mechanism: Unlike deposit functions (which have a check verifying that `msg.value == 0`), the output ERC20 transfer routines do not guard against incoming native assets (ETH or AVAX). This allows callers to attach native value to standard ERC20 outbound transfers. Furthermore, neither standard router contract has admin, public owner, or recovery functions to withdraw accidentally sent assets.
- Impact: Any ETH or AVAX accidentally or erroneously attached to ERC20 outbound transfers becomes permanently locked inside the router contracts with no recovery option available.
