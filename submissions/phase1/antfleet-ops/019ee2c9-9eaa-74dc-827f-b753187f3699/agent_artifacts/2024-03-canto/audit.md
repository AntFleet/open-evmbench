# Audit: 2024-03-canto

## Unauthenticated `lzCompose` lets arbitrary callers drain router-held tokens
- Location: [audit_sources/2024-03-canto/contracts/asd/asdRouter.sol](/Users/augstar/open-evmbench/audit_sources/2024-03-canto/contracts/asd/asdRouter.sol:61) : `lzCompose`
- Mechanism: `lzCompose` is externally callable and never verifies that `msg.sender` is the LayerZero endpoint/executor or that `_from` / `_message` came from a trusted peer. It immediately trusts attacker-controlled compose data, and on the `composeMsg.length != 224` branch it calls `_refundToken` with caller-controlled `_from`, `amountLD`, and `composeFrom` before any whitelist check. That means anyone can forge a fake compose packet and make the router transfer whatever ERC20 balance it currently holds for `_from` to an arbitrary address. The same missing authentication also leaves the success/failure paths callable with fully attacker-chosen payloads.
- Impact: An attacker can steal any tokens sitting in `ASDRouter` from prior failed routes, accidental transfers, or stuck balances, including non-whitelisted assets, simply by calling `lzCompose` directly with crafted calldata.

## `withdrawCarry` ignores omnichain supply and can withdraw principal backing bridged holders
- Location: [audit_sources/2024-03-canto/contracts/asd/asdOFT.sol](/Users/augstar/open-evmbench/audit_sources/2024-03-canto/contracts/asd/asdOFT.sol:63) : `withdrawCarry`
- Mechanism: `ASDOFT` is an OFT, so bridging burns supply on the source chain and mints it on another chain. `withdrawCarry` computes surplus as `balanceOfUnderlying(this) - totalSupply()`, but `totalSupply()` is only the local chain’s supply. Once users bridge `asD` off Canto, local supply drops while the Canto `cNOTE` collateral still backs the global supply. The owner can then treat bridged-out principal as “carry” and redeem it.
- Impact: The owner can drain underlying that is still needed to back `asD` circulating on other chains, leaving remote holders undercollateralized and potentially unable to redeem after bridging back.

## `asdUSDC` makes all whitelisted USDC versions fungible at par, so a weak version can drain strong reserves
- Location: [audit_sources/2024-03-canto/contracts/asd/asdUSDC.sol](/Users/augstar/open-evmbench/audit_sources/2024-03-canto/contracts/asd/asdUSDC.sol:34) : `deposit`, [audit_sources/2024-03-canto/contracts/asd/asdUSDC.sol](/Users/augstar/open-evmbench/audit_sources/2024-03-canto/contracts/asd/asdUSDC.sol:52) : `withdraw`
- Mechanism: `deposit` mints a single fungible `asdUSDC` balance based only on decimal normalization, with no distinction for which underlying version was supplied. `withdraw` then lets a holder redeem that fungible balance for any whitelisted version they choose. The code therefore assumes every whitelisted USDC representation is permanently equivalent 1:1 in value and backing, which is unsafe for bridge wrappers or issuer-specific versions.
- Impact: If any whitelisted USDC version is depegged, compromised, or inflated, an attacker can deposit that bad version and withdraw a healthier one, draining the good reserves from the pool.

