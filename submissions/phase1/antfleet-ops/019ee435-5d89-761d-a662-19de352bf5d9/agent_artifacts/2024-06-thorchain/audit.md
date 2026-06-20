# Audit: 2024-06-thorchain

Findings refer to the non-`chain/` paths; the same vulnerable code is duplicated under `chain/...`.

## Rebasing tokens corrupt router vault accounting
- Location: `ethereum/contracts/THORChain_Router.sol` : `_deposit`, `transferOut`, `transferAllowance`, `_routerDeposit`; `avalanche/src/contracts/AvaxRouter.sol` : `deposit`, `transferOut`, `transferAllowance`, `_routerDeposit`
- Mechanism: The routers credit fixed `_vaultAllowance[vault][asset]` amounts when tokens are deposited, but hold all token balances pooled in the router. For rebasing tokens, the router’s actual token balance changes globally while each vault’s recorded allowance stays unchanged. A user can deposit before a negative rebase and later withdraw or migrate the same nominal allowance, consuming a larger share of the router’s now-smaller pooled balance.
- Impact: An attacker can steal value from other vaults/users that share the same rebasing asset balance in the router; positive rebases can also leave accounting mismatches and locked funds.

## Fee-on-transfer outbounds overstate delivered tokens
- Location: `ethereum/contracts/THORChain_Router.sol` : `transferOut`, `_transferOutV5`, `_transferOutAndCallV5`; `avalanche/src/contracts/AvaxRouter.sol` : `transferOut`
- Mechanism: Deposits measure the actual received amount with balance deltas, but outbound ERC20 paths do not. They decrement vault allowance and emit events for the nominal `amount`/`fromAmount` even if the token charges a transfer fee and the recipient or aggregator receives less. In the Ethereum V5 aggregator path, the router transfers `fromAmount` to the aggregator, then calls `swapOutV5` with the same nominal amount and ignores `_dexAggSuccess`; a fee-on-transfer token can make the aggregator revert because it received less than `fromAmount`.
- Impact: Users can be underpaid while THORChain observes a successful full-amount outbound; V5 ERC20 outbounds can strand tokens in the aggregator after consuming vault allowance.

## Failed native transfers emit successful recipient events
- Location: `ethereum/contracts/THORChain_Router.sol` : `transferOut`, `_transferOutV5`, `transferOutAndCall`; `avalanche/src/contracts/AvaxRouter.sol` : `transferOut`, `transferOutAndCall`
- Mechanism: Native ETH/AVAX sends use `.send`. When the send to the requested recipient fails, the code bounces the value back to `msg.sender`, but still emits `TransferOut`/`TransferOutAndCall` with the original recipient and amount. The event therefore says the outbound reached the user even though the value returned to the vault.
- Impact: THORChain/Bifrost can mark an outbound as completed to the user when the user received nothing, causing incorrect protocol accounting and user loss.

## V5 ETH aggregator failure sends funds to the aggregator target
- Location: `ethereum/contracts/THORChain_Router.sol` : `_transferOutAndCallV5`
- Mechanism: In the native ETH V5 path, if `target.swapOutV5(...)` fails, the fallback sends `msg.value` to `aggregationPayload.target` instead of `aggregationPayload.recipient`, then emits `TransferOutAndCallV5` naming the intended recipient. A reverting aggregator with a payable `receive` function will keep the ETH.
- Impact: Failed aggregator calls can leave the full outbound ETH at the aggregator contract while THORChain records the recipient as paid.

## `transferTo` allows phishing contracts to drain ETH.RUNE
- Location: `ethereum/contracts/eth_rune.sol` : `transferTo`
- Mechanism: `transferTo` transfers tokens from `tx.origin` rather than from `msg.sender` or an approved allowance. Any contract called by an ETH.RUNE holder can call `transferTo(attacker, amount)` during that transaction and move the origin account’s tokens.
- Impact: A malicious dApp or phishing contract can steal ETH.RUNE from users who interact with it, without prior token approval.

