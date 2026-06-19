# Audit: 2024-03-canto

I found two genuine security vulnerabilities in the supplied contracts.

## Unauthenticated LayerZero compose execution lets attackers drain router-held tokens
- Location: `contracts/asd/asdRouter.sol` : `lzCompose`
- Mechanism: `lzCompose` is externally callable and never verifies that `msg.sender` is the trusted LayerZero endpoint/executor, nor that the compose message was actually delivered by LayerZero. The function trusts caller-supplied `_from`, `_message`, and payload data, then approves and deposits `_from` tokens from the router into `asdUSDC`, swaps them, mints ASD, and sends/refunds to attacker-controlled addresses. The only meaningful check is that `_from` is a whitelisted USDC version, but that does not authenticate the message or prove the router’s token balance belongs to the caller.
- Impact: An attacker can call `lzCompose` directly with a forged compose payload and steal any whitelisted USDC/OFT balance currently held by the router, including tokens temporarily present during legitimate compose flows or tokens accidentally stuck in the contract. They can direct the resulting NOTE/ASD or refund path to their own address.

## Fungible multi-USDC wrapper allows bad collateral to drain good collateral
- Location: `contracts/asd/asdUSDC.sol` : `deposit`, `withdraw`
- Mechanism: `ASDUSDC` mints one fungible `asdUSDC` token against multiple distinct whitelisted USDC versions, but withdrawals let the holder choose any whitelisted backing asset. The contract accounts balances per USDC version, yet the minted claim is not tied to the deposited version and there is no oracle, risk isolation, depeg handling, or per-asset share accounting.
- Impact: If any whitelisted USDC version becomes impaired, depegs, freezes, or is otherwise worth less than another whitelisted version, an attacker can deposit the weak version, receive fully fungible `asdUSDC`, and withdraw the stronger USDC version until that reserve is drained.

