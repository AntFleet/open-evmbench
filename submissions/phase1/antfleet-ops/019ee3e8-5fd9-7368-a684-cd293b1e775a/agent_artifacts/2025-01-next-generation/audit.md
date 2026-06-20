# Audit: 2025-01-next-generation

### Unprotected Function

- Location: `Token.sol` : `setTxFeeRate`
- Mechanism: The function `setTxFeeRate` can be called by any address with the `ADMIN` role without any rate validation checks beyond the ones defined in `FeesHandlerUpgradeable`. However, there's no validation to check if the new rate is too high, which could lead to unintended high fees being charged to users.
- Impact: An attacker with the `ADMIN` role could set an extremely high transaction fee rate, effectively denying service to users who cannot afford such high fees.

### Unvalidated Input

- Location: `ERC20MetaTxUpgradeable.sol` : `permit`
- Mechanism: The `permit` function does not validate if the `spender` is a contract or an EOA. If the `spender` is a contract, it might not be able to handle the permitted amount correctly.
- Impact: This could lead to unintended behavior or errors when the `spender` tries to use the permitted amount, potentially causing financial losses.

### Potential Reentrancy

- Location: `FeesHandlerUpgradeable.sol` : `_payTxFee`
- Mechanism: The `_payTxFee` function calls `_update` which in turn might trigger another contract's function if the recipient is a contract. This could potentially lead to reentrancy attacks if not properly handled.
- Impact: An attacker could exploit this to drain the contract of funds by repeatedly triggering the `_payTxFee` function in a reentrant manner.

### Missing Access Control

- Location: `Forwarder.sol` : `execute`
- Mechanism: The `execute` function does not check if the `req.to` address has the necessary permissions or roles to execute the transaction on behalf of the `req.from` address.
- Impact: An attacker could potentially execute transactions on behalf of another user without proper authorization.

### Use of `transfer` instead of `safeTransfer`

- Location: `Token.sol` : `payGaslessBasefee`
- Mechanism: The function uses the `transfer` function to send funds, which can fail if the recipient is a contract that does not support receiving Ether.
- Impact: This could lead to the contract being unable to send funds to certain recipients, potentially causing financial losses.

### Potential Front-Running Attacks

- Location: `FeesHandlerUpgradeable.sol` : `setTxFeeRate`
- Mechanism: The `setTxFeeRate` function can be front-run by an attacker who notices a pending transaction to update the fee rate. The attacker can update the fee rate to a higher value before the pending transaction is executed.
- Impact: This could lead to the attacker earning higher fees than intended, potentially causing financial losses to the contract or its users.

### Unsecured Use of `tx.origin`

- Location: None, but the contract uses `_msgSender()` which is secure. However, it's worth noting that if `tx.origin` were used instead, it would be a security vulnerability.
- Mechanism: Using `tx.origin` instead of `_msgSender()` can make a contract vulnerable to phishing attacks.
- Impact: An attacker could trick a user into calling a function on a contract, allowing the attacker to execute arbitrary code on behalf of the user.

Note that the code provided seems to be well-structured and secure, with proper use of OpenZeppelin's contracts and secure coding practices. However, it's always important to keep in mind potential security vulnerabilities and to continually review and audit the code to ensure its security and integrity.
