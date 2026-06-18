# Audit: 2025-01-next-generation

# Security Audit Report

## 1. Signature verification bypass for `address(0)` in meta‑transactions
- **Location:** `ERC20MetaTxUpgradeable.sol` : `transferWithAuthorization` and `Forwarder.sol` : `_verifySig`
- **Mechanism:**  
  Both functions check that the recovered signer equals a user‑supplied address (`holder` / `req.from`). When the supplied address is `address(0)`, an attacker can craft an invalid signature that causes `ECDSA.recover` to return `address(0)`, making the equality check pass. This completely bypasses the signature verification for the zero address.
- **Impact:**  
  In the current codebase, `transferWithAuthorization` is overridden to call `transferSanity`, which checks the balance of `holder` and deducts fees. Because `balanceOf(address(0))` is always zero, any attempt with `value > 0` will revert. However, the verification flaw remains latent; if the fee logic were ever removed or bypassed, an attacker could mint tokens by calling `_update(address(0), spender, value)`. The same flaw exists in the Forwarder’s `_verifySig`, but the token’s `transfer` is similarly protected by the balance check. The vulnerability undermines the integrity of meta‑transaction authentication.

## 2. Tokens can be minted directly to the token contract, permanently locking them
- **Location:** `ERC20ControlerMinterUpgradeable.sol` : `mint`
- **Mechanism:**  
  The `mint` function allows minting tokens to any address, including the token contract itself (`address(this)`). The `adminSanity` check (used in normal transfers) explicitly prevents transfers to the token contract, but `mint` does not call `adminSanity` and thus has no such restriction.
- **Impact:**  
  A minter can mint tokens to the token contract. Once there, those tokens can never be transferred out because every transfer function reverts with `TransferToContractError`. This effectively burns the tokens and can be used to manipulate the total supply or to grief the protocol. The risk is moderate because only trusted minters can call `mint`, but the design flaw is still a real vulnerability.

## 3. `setAdministrator` and `setOwner` can leave excess role members with privileged access
- **Location:** `ERC20AdminUpgradeable.sol` : `setAdministrator` and `Token.sol` : `setOwner`
- **Mechanism:**  
  Both functions assume the role has exactly one member and revoke only the first member (`getRoleMember(role, 0)`). If the role was previously granted to multiple addresses (e.g., via direct `grantRole` calls by the admin), the function will remove only the first member, leaving the others with the role.
- **Impact:**  
  An attacker who was previously granted the ADMIN or OWNER role could retain access after a supposed change of administrator, allowing them to persist in privileged actions such as pausing, blacklisting, fee changes, or contract upgrades. This is a logic error in role management that can lead to unauthorized long‑term access.

## 4. `setMasterMinter` can lock minter management by setting `address(0)`
- **Location:** `ERC20ControlerMinterUpgradeable.sol` : `setMasterMinter`
- **Mechanism:**  
  The function does not check that `newMasterMinter` is not `address(0)`. If called with the zero address, the `MASTER_MINTER` role is granted to `address(0)`, which cannot sign transactions. Subsequently, functions protected by `onlyRole(MASTER_MINTER)` (e.g., `addMinter`, `removeMinter`, `updateMintingAllowance`) become permanently inaccessible.
- **Impact:**  
  If the owner accidentally sets the master minter to `address(0)`, minter management is locked forever (unless the owner can still call `setMasterMinter` again). This could lead to a denial of service where no new minters can be added or adjusted, breaking the minting mechanism.

## 5. `forceTransfer` bypasses transaction fee deduction
- **Location:** `ERC20AdminUpgradeable.sol` : `forceTransfer`
- **Mechanism:**  
  The `forceTransfer` function allows an ADMIN to move tokens directly via `_update` without calling `_payTxFee`. Normal transfers always deduct a percentage fee (if the fee rate is non‑zero) before moving the tokens.
- **Impact:**  
  An ADMIN can transfer tokens without paying the configured fee. If the ADMIN role is compromised, an attacker could drain user funds without paying fees, undermining the fee‑collection mechanism. Even if the ADMIN is trusted, this creates an unfair privilege that can be abused.
