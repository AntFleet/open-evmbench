# Audit: 2024-06-thorchain

Below are the genuine security issues I found. The token fixtures (`Token.sol`, `USDT.sol`, `WETH.sol`, `EvilToken`, `StealToken`, `EvilCallback`, `RevertingContract`, `SushiRouterSmol`) are standard or test-harness contracts; the reentrancy guards on the routers correctly neutralize the `EvilToken`/`EvilCallback` reentry attempts, so those are negative tests, not live bugs. The findings worth reporting are in the production router/aggregator and in `eth_rune.sol`.

## `tx.origin`-based transfer authorization in ETH.RUNE
- Location: `ethereum/contracts/eth_rune.sol` (and `chain/ethereum/contracts/eth_rune.sol`) : `ETH_RUNE.transferTo`
- Mechanism: `transferTo(recipient, amount)` calls `_transfer(tx.origin, recipient, amount)`. It moves tokens out of `tx.origin` with no allowance check and no `msg.sender` relationship. Authorization is based entirely on `tx.origin`, so the move is attributed to whoever originated the transaction rather than to the contract actually invoking it.
- Impact: Any contract that a RUNE holder is induced to call (a phishing/airdrop/NFT-mint front) can, in that same transaction, call `ETH_RUNE.transferTo(attacker, victimBalance)` and drain the victim's entire RUNE balance without any prior approval. The in-source comment acknowledges the risk, but it is a real, externally exploitable theft primitive against ordinary users.

## V5 aggregator-call failure path loses / misdirects funds (no refund to recipient)
- Location: `ethereum/contracts/THORChain_Router.sol` (and `chain/ethereum/...`) : `_transferOutAndCallV5`
- Mechanism: 
  - ERC20 branch: the router decrements `_vaultAllowance[msg.sender][fromAsset]`, `transfer`s `fromAmount` to `target`, then calls `target.swapOutV5(...)` and **ignores the return value** (`_dexAggSuccess` is unused). If `swapOutV5` reverts (e.g., the `THORChain_Failing_Aggregator` pattern, or any aggregator revert), the tokens are already sitting in `target` and are never returned; the recipient receives nothing and the allowance is permanently consumed.
  - ETH branch: on `!swapOutSuccess` it does `payable(target).send(msg.value)` — it returns the ETH to the **aggregator target**, not to `recipient`, and only bounces to `msg.sender` if that send also fails. This diverges from the V4 `transferOutAndCall`, which on failure sends to the recipient (`to`).
- Impact: A failed outbound swap strands the user's outbound funds inside the aggregator contract instead of delivering them to the recipient or bouncing them back to the vault. Recovery depends on the aggregator's `rescueFunds` (onlyOwner), so the end user has no on-chain path to their funds. This is an accounting/loss bug, not merely a "swap didn't happen" no-op.

## `swapIn` deposits the full contract balance, sweeping stranded funds
- Location: `ethereum/contracts/THORChain_Aggregator.sol` and `avalanche/src/contracts/AvaxAggregator.sol` : `swapIn`
- Mechanism: after the DEX swap, the function sets `_safeAmount = address(this).balance` and forwards that entire balance into `depositWithExpiry{value: _safeAmount}`. It does not isolate the amount produced by this specific swap. Because the aggregator has a payable `receive()` and may hold residual ETH/AVAX (e.g., dust left by a prior failed/rounding swap, or funds parked for `rescueFunds`), the caller's deposit is inflated by whatever balance happens to be present.
- Impact: A caller can opportunistically sweep any ETH/AVAX stranded in the aggregator into their own THORChain deposit memo, claiming funds that do not belong to that swap. Severity is limited (only funds that have accumulated in the permissionless aggregator), but it is a real misappropriation-of-stranded-funds path rather than intended behavior.

## Notes on items that are *not* vulnerabilities here
- The ERC20 custody model in `THORChain_Router`/`AvaxRouter` is sound: every outbound ERC20 path (`transferOut`, `_transferOutV5`, `_transferOutAndCallV5`, `_adjustAllowances`, `_routerDeposit`) decrements `_vaultAllowance[msg.sender][asset]` under Solidity 0.8 checked arithmetic, so an attacker with zero allowance cannot move deposited tokens (the subtraction reverts). Deposits only credit allowance equal to tokens actually received.
- The reentrancy attempts modeled by `EvilToken.transferFrom` (reentering `deposit`) and `EvilCallback.receive` (reentering `transferAllowance`) are both blocked because all allowance-mutating entry points (`deposit`/`_deposit`, `transferAllowance`, `transferOut*`, `returnVaultAssets`) carry the `nonReentrant` guard. The guard is load-bearing for the balance-delta accounting in `safeTransferFrom`, and it is present.
- The lack of an on-chain aggregator whitelist in `transferOutAndCall*` is by design (matching/whitelisting is performed off-chain by Bifrost) and the calls are vault-gated, so it is not independently exploitable from these contracts.

