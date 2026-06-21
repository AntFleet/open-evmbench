# Audit: 2024-06-thorchain

## Malicious ERC20 `transfer` drains unrelated router-held tokens
- Location: `chain/ethereum/contracts/THORChain_Router.sol` : `transferOut`, `_transferOutAndCallV5`
- Mechanism: Outbound ERC20 payouts use a low-level `transfer(address,uint256)` call and only validate the return value of that single transfer. A malicious or non-standard token can execute arbitrary logic inside `transfer`, including transferring additional tokens held by the router. `StealERC20Token` demonstrates this: its `transfer` forwards a second `transfer` on a separate `target` token from `msg.sender` (the router). Because the router pools ERC20 balances for all vault allowances in one contract balance, one vault’s `transferOut` of a malicious token can pull other tokens held for different vaults without decrementing those vaults’ allowances.
- Impact: An attacker who can cause a THORChain vault to outbound a malicious ERC20 (or who lists such a token) can drain arbitrary other ERC20 assets custodied by the router, stealing funds belonging to other vaults/users.

## Malicious ERC20 `transfer` drains router tokens during aggregator payout
- Location: `chain/avalanche/src/contracts/AvaxRouter.sol` : `transferOut`
- Mechanism: `AvaxRouter` uses the same unsafe low-level ERC20 `transfer` pattern as the Ethereum router. During `transferOut`, the router is `msg.sender` on the token’s `transfer`, so a malicious token can trigger additional transfers out of the router’s balance while the router only debits allowance for the nominal outbound asset.
- Impact: Same as above on Avalanche: unrelated ARC-20 assets custodied by the router can be stolen during a malicious-token outbound transfer.

## ETH swap failure in `transferOutAndCallV5` refunds the aggregator instead of the recipient
- Location: `chain/ethereum/contracts/THORChain_Router.sol` : `_transferOutAndCallV5`
- Mechanism: In the native-asset branch, if the aggregator `swapOutV5` call fails, the fallback sends `msg.value` to `aggregationPayload.target` (the aggregator contract), not to `aggregationPayload.recipient`. The inline comment says the recipient should receive the gas asset, but the code sends it to the target. This is a regression from V4 `transferOutAndCall`, which correctly falls back to `payable(to).send(...)`.
- Impact: When a swap fails, outbound ETH is sent to the aggregator contract instead of the intended recipient. A malicious or buggy aggregator can deliberately fail swaps and capture refunded ETH; even with a honest aggregator, users lose access to funds unless manually recovered via `rescueFunds`.

## `swapOutV5` ignores `toAsset` for ERC20 inputs and always pays out ETH
- Location: `chain/ethereum/contracts/THORChain_Aggregator.sol` : `swapOutV5`
- Mechanism: In the ERC20 input branch (`fromAsset != address(0)`), the aggregator builds a path `fromAsset -> WETH` and calls `swapExactTokensForETH`, sending output directly to `recipient`. The `toAsset` argument is never used, so token-to-token swaps are not performed. The ETH input branch correctly swaps to `toAsset` via `swapExactETHForTokens`.
- Impact: Any THORChain outbound flow that routes ERC20 through `transferOutAndCallV5` expecting delivery of `toAsset` (e.g., USDC → DAI) instead delivers ETH to the recipient. Recipients receive the wrong asset, causing direct fund loss / failed cross-chain settlement relative to the intended swap.

## `batchTransferOutAndCallV5` forwards the full `msg.value` on every native swap
- Location: `chain/ethereum/contracts/THORChain_Router.sol` : `batchTransferOutAndCallV5`, `_transferOutAndCallV5`
- Mechanism: For native-asset entries, each loop iteration calls the aggregator with `{value: msg.value}`, forwarding the entire transaction `msg.value` every time. `msg.value` is fixed for the whole transaction and is not split across batch items. The first native outbound therefore consumes the full attached ETH; later items either fail or behave unpredictably depending on pre-existing router balance. Unlike `batchTransferOutV5`, which uses per-item `amount`, the batch aggregator path has no per-item ETH accounting.
- Impact: Batched native outbound swaps misallocate ETH: the first recipient/aggregator can receive the entire batch’s ETH, while later intended recipients receive nothing. This breaks batch settlement and can cause large user fund misdelivery.

## Outbound ERC20 accounting does not reconcile actual transferred amounts
- Location: `chain/ethereum/contracts/THORChain_Router.sol` : `transferOut`, `_transferOutAndCallV5`, `_routerDeposit`
- Mechanism: Inbound deposits use `safeTransferFrom`, which credits vault allowance based on the router’s actual balance increase. Outbound ERC20 flows debit `_vaultAllowance` by the nominal `amount` / `fromAmount` before/without verifying how many tokens were actually moved. Fee-on-transfer, deflationary, or otherwise non-standard ERC20s can cause the router to lose more tokens than accounted for, or to debit a vault for tokens that never arrived at the destination/aggregator.
- Impact: Vault accounting can diverge from real token balances. Vaults can be over-debited, outbound swaps can fail with tokens stranded, and aggregate router inventory can become insolvent relative to recorded allowances.

## Failed ERC20 aggregator swaps strand tokens with no vault refund path
- Location: `chain/ethereum/contracts/THORChain_Router.sol` : `_transferOutAndCallV5`; `chain/ethereum/contracts/THORChain_Aggregator.sol` : `swapOutV5`
- Mechanism: In the ERC20 branch of `_transferOutAndCallV5`, the router first debits vault allowance and transfers `fromAmount` tokens to the aggregator, then calls `swapOutV5`. The router intentionally does not revert if the aggregator call fails. On the aggregator side, the ERC20 branch uses `require(aggSuccess, "swapExactTokensForETH failed")`, so a failed swap reverts inside the aggregator call and leaves tokens sitting in the aggregator. There is no router logic to claw back stranded tokens to the debited vault; recovery depends on aggregator `owner` calling `rescueFunds`.
- Impact: If the DEX swap fails (liquidity, slippage, bad path, fee-on-transfer mismatch, or a failing aggregator such as `THORChain_Failing_Aggregator`), vault tokens are debited and trapped in the aggregator. Funds are lost to the vault until manual owner intervention, and a malicious aggregator owner can permanently steal them.

## `ETH_RUNE.transferTo` enables approval-less theft via `tx.origin` phishing
- Location: `chain/ethereum/contracts/eth_rune.sol` : `transferTo`
- Mechanism: `transferTo` transfers tokens from `tx.origin` rather than `msg.sender`, enabling approval-less transfers. The contract itself documents that phishing contracts can intercept `tx.origin` and drain users who interact with a malicious intermediary while `transferTo` is invoked.
- Impact: Users can be phished into interacting with a malicious contract that calls `transferTo` and drains their `ETH_RUNE` balance to an attacker-controlled recipient.

## Reentrancy during ERC20 deposit can inflate vault allowances (blocked only by guard)
- Location: `chain/ethereum/contracts/EvilToken.sol` : `transferFrom`; `chain/ethereum/contracts/THORChain_Router.sol` : `deposit` / `_deposit`
- Mechanism: `EvilERC20Token.transferFrom` mints balance/allowance to itself and reenters the router’s `deposit` during the token transfer that is part of `_deposit`’s `safeTransferFrom`. The nested deposit credits the depositor address as the vault using inflated token balance. This is the classic THORChain “evil token” deposit reentrancy pattern. In this codebase it is prevented because `deposit` / `_deposit` are `nonReentrant`; if that guard were absent or bypassed on any deposit path, the nested call would succeed.
- Impact: Without the reentrancy guard, an attacker could credit themselves arbitrary vault allowance without depositing real assets, then call `transferOut` to steal genuine tokens custodied by the router. The guard mitigates this in the provided code, but the token behavior remains a live compatibility hazard for any unguarded deposit path.

## ETH receive callback can reenter router during outbound transfers (blocked only by guard)
- Location: `chain/ethereum/contracts/EvilCallback.sol` : `receive`; `chain/ethereum/contracts/THORChain_Router.sol` : `transferOut`
- Mechanism: `transferOut` sends native assets with `send`, executing the recipient’s fallback/receive in the middle of the outbound flow. `EvilCallback.receive` reenters the router and calls `transferAllowance` to emit a misleading zero-value `TransferAllowance` event during the same transaction as a real vault outbound. In this codebase, `transferAllowance` is `nonReentrant`, so the callback reverts and the outer `send` fails, bouncing ETH back to the vault; however, the pattern shows reliance on reentrancy guards rather than strict checks-effects-interactions around ETH sends.
- Impact: On any router variant where outbound ETH transfers invoke recipient code before completion and not every reachable state-changing function is guarded, an attacker contract receiving vault ETH could reenter to emit spoofed accounting events or manipulate intermediate router state, potentially confusing off-chain THORChain observers and enabling cross-function exploits.

