# Audit: 2025-01-next-generation

# Security Audit Report

## Burn bypasses pause and blacklist restrictions
- Location: `ERC20ControlerMinterUpgradeable.sol` : `burn`
- Mechanism: `burn` only checks the `_operating` flag and the minter role, but never calls `adminSanity` or checks `paused()` / `isBlacklisted(_msgSender())`. A minter whose account has been blacklisted can still burn their own tokens, and any minter can burn while the contract is paused. This directly defeats the purpose of blacklisting (which is enforced in `adminSanity` for transfers) — a blacklisted minter can destroy their balance before the ADMIN can seize it via `forceTransfer`.
- Impact: Blacklisted minters can destroy their token holdings to avoid seizure; minters can burn while the contract is paused, circumventing the pause mechanism's intent to freeze all token movement.

## Mint does not validate recipient against blacklist or contract address
- Location: `ERC20ControlerMinterUpgradeable.sol` : `mint`
- Mechanism: `mint(address to, uint256 amount)` calls `_mint(to, amount)` without any check on `to`. It does not verify whether `to` is blacklisted or whether `to == address(this)`. Since `adminSanity` (called on every transfer/transferFrom/forceTransfer) reverts when `to == address(this)`, any tokens minted to the contract address become permanently locked with no mechanism to recover them.
- Impact: A minter can permanently lock tokens by minting to the contract address. A minter can also mint to blacklisted accounts, undermining the blacklist enforcement model.

## `payGaslessBasefee` bypasses all sanity checks
- Location: `Token.sol` : `payGaslessBasefee`
- Mechanism: `payGaslessBasefee` is restricted to the trusted forwarder (`isTrustedForwarder(msg.sender)`) but then calls `_update(payer, paymaster, _gaslessBasefee)` directly, without going through `adminSanity` or `transferSanity`. This means the token movement bypasses pause checks, sender/recipient blacklist checks, the `to == address(this)` guard, and the fee deduction logic. Any contract that is set as the trusted forwarder can call `payGaslessBasefee` to move `_gaslessBasefee` tokens from any payer to any paymaster, regardless of pause or blacklist state.
- Impact: If the trusted forwarder contract has any callable path to `payGaslessBasefee` (beyond the intended post-transfer call in `execute`), or if the trusted forwarder is ever changed to a contract with broader functionality, tokens can be moved from blacklisted or paused accounts without restriction.

## `adminSanity` does not guard against `address(0)`, enabling mint/burn via `forceTransfer` and accidental burns via `transfer`
- Location: `ERC20AdminUpgradeable.sol` : `adminSanity` / `forceTransfer`
- Mechanism: `adminSanity` checks `to == address(this)` but does not check `from == address(0)` or `to == address(0)`. In OpenZeppelin 5.x, `_update(address(0), to, amount)` mints tokens and `_update(from, address(0), amount)` burns tokens. Therefore: (a) `forceTransfer(address(0), to, amount)` — callable only by ADMIN but with no amount cap — mints unlimited tokens, completely bypassing the minter allowance system; (b) `forceTransfer(from, address(0), amount)` burns any user's tokens; (c) regular `transfer(address(0), amount)` burns the caller's tokens without reverting, which is non-standard ERC20 behavior that can cause accidental permanent loss and break integrations expecting a revert.
- Impact: ADMIN can mint unlimited tokens via `forceTransfer(address(0), …)`, sidestepping the entire minting allowance framework. ADMIN can destroy any user's tokens via `forceTransfer(…, address(0), …)`. Any user can irreversibly burn their own tokens by transferring to `address(0)`, unlike standard ERC20 which reverts.

## Forwarder relay transactions are front-runnable
- Location: `Forwarder.sol` : `execute`
- Mechanism: `execute` is an unpermissioned `external payable` function. Any party observing a valid signed `ForwardRequest` in the mempool can submit it themselves. The `_eurf.payGaslessBasefee(req.from, _msgSender())` call pays the gasless basefee to whoever calls `execute`, so an attacker can front-run the intended relayer and collect the basefee reward without performing the intended relayer service.
- Impact: Griefing of legitimate relayers — an attacker can steal the `payGaslessBasefee` payment by front-running relay transactions, disincentivizing relayer participation.
