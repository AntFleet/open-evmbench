# Audit: 2026-01-tempo-mpp-streams

### Reentrancy Vulnerability in `settle` Function
- Location: `TempoStreamChannel.sol` : `settle`
- Mechanism: The `settle` function is vulnerable to reentrancy attacks. Although the `nonReentrant` modifier is used, which should prevent reentrancy, the function still transfers tokens to the payee before updating the channel's state. An attacker could exploit this by reentering the contract and causing it to transfer more tokens than intended.
- Impact: An attacker could drain the channel's deposit by reentering the contract and settling vouchers multiple times, potentially stealing funds from the payer.

### Unprotected Function in `initiateClose`
- Location: `TempoStreamChannel.sol` : `initiateClose`
- Mechanism: The `initiateClose` function does not have any access control or checks for the caller's identity. This means that anyone can initiate the closure of a channel, not just the payer or payee.
- Impact: An attacker could initiate the closure of a channel without the knowledge or consent of the payer or payee, potentially causing unintended consequences such as the loss of funds or the inability to settle vouchers.

### Unprotected Function in `close`
- Location: `TempoStreamChannel.sol` : `close`
- Mechanism: The `close` function allows the cooperative closure of a channel with the settlement of a final voucher. However, it does not check if the voucher's `cumulativeAmount` is greater than the channel's `deposit`. This could lead to an incorrect distribution of funds.
- Impact: An attacker could exploit this by providing a voucher with a `cumulativeAmount` that exceeds the channel's `deposit`, potentially causing the contract to transfer more tokens than intended to the payee, or to transfer tokens to the wrong address.

### Unvalidated Input in `openChannel`
- Location: `TempoStreamChannel.sol` : `openChannel`
- Mechanism: The `openChannel` function does not validate the `token` parameter to ensure it is a valid TIP-20 token contract. This could lead to incorrect behavior or errors if an invalid token contract is provided.
- Impact: An attacker could exploit this by providing a malicious token contract that interferes with the normal functioning of the `TempoStreamChannel` contract.

### Unvalidated Input in `addDeposit`
- Location: `TempoStreamChannel.sol` : `addDeposit`
- Mechanism: The `addDeposit` function does not check if the `amount` parameter is greater than zero. This could lead to incorrect behavior or errors if a non-positive amount is provided.
- Impact: Although the function reverts if the `amount` is zero, it does not prevent an attacker from providing a negative amount, which could potentially cause errors or incorrect behavior.

### Unprotected Function in `getAvailableBalance`
- Location: `TempoStreamChannel.sol` : `getAvailableBalance`
- Mechanism: The `getAvailableBalance` function does not check if the channel exists or if it has been finalized. This could lead to incorrect results or errors if a non-existent or finalized channel is queried.
- Impact: An attacker could exploit this by querying the available balance of a non-existent or finalized channel, potentially causing errors or incorrect behavior.

### Unvalidated Input in `getChannel`
- Location: `TempoStreamChannel.sol` : `getChannel`
- Mechanism: The `getChannel` function does not check if the channel exists or if it has been finalized. This could lead to incorrect results or errors if a non-existent or finalized channel is queried.
- Impact: An attacker could exploit this by querying a non-existent or finalized channel, potentially causing errors or incorrect behavior.

### Lack of Access Control in `finalize`
- Location: `TempoStreamChannel.sol` : `finalize`
- Mechanism: The `finalize` function does not check the identity of the caller, allowing anyone to finalize a channel.
- Impact: An attacker could finalize a channel without the knowledge or consent of the payer or payee, potentially causing unintended consequences such as the loss of funds or the inability to settle vouchers.
