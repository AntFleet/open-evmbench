# Audit: 2024-03-canto

### Reentrancy Vulnerability
- Location: contracts/asd/asdOFT.sol : `mint` function
- Mechanism: The `mint` function approves and then calls the `mint` function on `cNoteToken` which can potentially lead to a reentrancy attack if `cNoteToken` is a malicious contract. 
- Impact: An attacker can exploit this vulnerability to drain the contract's funds or execute unintended behavior by reentering the `mint` function.

### Use of tx.origin
- Location: contracts/asd/asdOFT.sol : `withdrawCarry` function
- Mechanism: The `withdrawCarry` function uses the `onlyOwner` modifier which checks if the `tx.origin` is equal to the contract's owner. However, using `tx.origin` can be problematic because it can be spoofed by an attacker.
- Impact: An attacker can exploit this vulnerability by tricking the contract into thinking the owner is calling the function when in fact it's the attacker.

### Unprotected Function
- Location: contracts/asd/asdOFT.sol : `burn` function
- Mechanism: The `burn` function does not have any access control, allowing anyone to burn tokens and potentially drain the contract's funds.
- Impact: An attacker can exploit this vulnerability to burn tokens and drain the contract's funds.

### Integer Overflow
- Location: contracts/asd/asdUSDC.sol : `deposit` function
- Mechanism: The `deposit` function multiplies the deposited amount by `10 ** (this.decimals() - ERC20(_usdcVersion).decimals())` which can cause an integer overflow if the result exceeds the maximum value that can be represented by a uint256.
- Impact: An attacker can exploit this vulnerability to potentially mint a large amount of tokens and drain the contract's funds.

### Unsecured use of call
- Location: contracts/asd/asdRouter.sol : `_depositNoteToASDVault` function
- Mechanism: The `_depositNoteToASDVault` function uses the `call` function to call the `mint` function on the `_asdVault` contract. However, using `call` can be problematic because it can revert the transaction if the called contract reverts.
- Impact: An attacker can exploit this vulnerability by causing the `_asdVault` contract to revert and potentially draining the contract's funds.

### Missing input validation
- Location: contracts/asd/asdRouter.sol : `_swapOFTForNote` function
- Mechanism: The `_swapOFTForNote` function does not validate the input `_minAmountNote` which can cause the function to return incorrect results or revert if the input is invalid.
- Impact: An attacker can exploit this vulnerability by providing an invalid input and potentially draining the contract's funds.

### Insecure encoding
- Location: contracts/asd/asdRouter.sol : `_decodeOFTComposeMsg` function
- Mechanism: The `_decodeOFTComposeMsg` function decodes the `_message` parameter using the `OFTComposeMsgCodec` library. However, the decoding process is not secure and can be exploited by an attacker.
- Impact: An attacker can exploit this vulnerability by providing a maliciously encoded message and potentially draining the contract's funds.

### Missing checks for pool existence
- Location: contracts/asd/asdRouter.sol : `ambientPoolFor` function
- Mechanism: The `ambientPoolFor` function does not check if the pool exists before trying to access it. If the pool does not exist, the function will return an incorrect result.
- Impact: An attacker can exploit this vulnerability by providing a non-existent pool and potentially draining the contract's funds.

### Unvalidated ERC20 transfers
- Location: contracts/asd/asdUSDC.sol : `deposit` function
- Mechanism: The `deposit` function transfers ERC20 tokens from the user's wallet to the contract without validating the transfer. If the transfer fails, the function will revert.
- Impact: An attacker can exploit this vulnerability by causing the transfer to fail and potentially draining the contract's funds.

### Missing event emission
- Location: contracts/asd/asdOFT.sol : `mint` function
- Mechanism: The `mint` function does not emit an event when minting new tokens. This can make it difficult to track the contract's activity.
- Impact: An attacker can exploit this vulnerability by minting new tokens without anyone noticing.

### Missing checks for USDC version
- Location: contracts/asd/asdUSDC.sol : `deposit` function
- Mechanism: The `deposit` function does not check if the USDC version is valid before depositing tokens. If an invalid USDC version is provided, the function will revert.
- Impact: An attacker can exploit this vulnerability by providing an invalid USDC version and potentially draining the contract's funds.

### Unsecured use of approve
- Location: contracts/asd/asdOFT.sol : `mint` function
- Mechanism: The `mint` function approves the `cNoteToken` contract to spend the user's tokens. However, using `approve` can be problematic because it can be exploited by an attacker.
- Impact: An attacker can exploit this vulnerability by approving the `cNoteToken` contract to spend the user's tokens and potentially draining the contract's funds.

### Missing checks for cNote token
- Location: contracts/asd/asdOFT.sol : `mint` function
- Mechanism: The `mint` function does not check if the `cNoteToken` contract is valid before minting new tokens. If an invalid `cNoteToken` contract is provided, the function will revert.
- Impact: An attacker can exploit this vulnerability by providing an invalid `cNoteToken` contract and potentially draining the contract's funds.

### Unvalidated ASD token transfers
- Location: contracts/asd/asdRouter.sol : `_sendASD` function
- Mechanism: The `_sendASD` function transfers ASD tokens to the destination receiver without validating the transfer. If the transfer fails, the function will revert.
- Impact: An attacker can exploit this vulnerability by causing the transfer to fail and potentially draining the contract's funds.

### Missing checks for messaging fee
- Location: contracts/asd/asdRouter.sol : `_sendASD` function
- Mechanism: The `_sendASD` function does not check if the messaging fee is valid before sending ASD tokens. If an invalid messaging fee is provided, the function will revert.
- Impact: An attacker can exploit this vulnerability by providing an invalid messaging fee and potentially draining the contract's funds.

### Insecure use of assembly
- Location: contracts/asd/asdRouter.sol : `_sendASD` function
- Mechanism: The `_sendASD` function uses assembly to encode the composed message. However, using assembly can be problematic because it can be exploited by an attacker.
- Impact: An attacker can exploit this vulnerability by providing a maliciously encoded message and potentially draining the contract's funds.

### Unsecured use of payable
- Location: contracts/asd/asdRouter.sol : `_sendASD` function
- Mechanism: The `_sendASD` function uses the `payable` keyword to send native tokens to the destination receiver. However, using `payable` can be problematic because it can be exploited by an attacker.
- Impact: An attacker can exploit this vulnerability by sending native tokens to the contract and potentially draining the contract's funds.

### Missing checks for cash address
- Location: contracts/asd/asdRouter.sol : `_refundToken` function
- Mechanism: The `_refundToken` function does not check if the cash address is valid before refunding tokens. If an invalid cash address is provided, the function will revert.
- Impact: An attacker can exploit this vulnerability by providing an invalid cash address and potentially draining the contract's funds.

### Unvalidated ERC20 token transfers
- Location: contracts/asd/asdRouter.sol : `_refundToken` function
- Mechanism: The `_refundToken` function transfers ERC20 tokens to the refund address without validating the transfer. If the transfer fails, the function will revert.
- Impact: An attacker can exploit this vulnerability by causing the transfer to fail and potentially draining the contract's funds.

### Missing event emission
- Location: contracts/asd/asdRouter.sol : `_refundToken` function
- Mechanism: The `_refundToken` function does not emit an event when refunding tokens. This can make it difficult to track the contract's activity.
- Impact: An attacker can exploit this vulnerability by refunding tokens without anyone noticing.

### Unsecured use of abicodetype function
- Location: contracts/asd/asdRouter.sol : `_decodeOFTComposeMsg` function
- Mechanism: The `_decodeOFTComposeMsg` function uses the `abi.decode` function to decode the composed message. However, using `abi.decode` can be problematic because it can be exploited by an attacker.
- Impact: An attacker can exploit this vulnerability by providing a maliciously encoded message and potentially draining the contract's funds.

### Missing checks for ambient pool index
- Location: contracts/asd/asdRouter.sol : `ambientPoolFor` function
- Mechanism: The `ambientPoolFor` function does not check if the ambient pool index is valid before accessing the pool. If an invalid ambient pool index is provided, the function will revert.
- Impact: An attacker can exploit this vulnerability by providing an invalid ambient pool index and potentially draining the contract's funds.

### Unvalidated ERC20 token balances
- Location: contracts/asd/asdUSDC.sol : `withdraw` function
- Mechanism: The `withdraw` function does not validate the ERC20 token balance before withdrawing tokens. If the balance is insufficient, the function will revert.
- Impact: An attacker can exploit this vulnerability by providing an invalid balance and potentially draining the contract's funds.

### Missing checks for USDC version
- Location: contracts/asd/asdUSDC.sol : `withdraw` function
- Mechanism: The `withdraw` function does not check if the USDC version is valid before withdrawing tokens. If an invalid USDC version is provided, the function will revert.
- Impact: An attacker can exploit this vulnerability by providing an invalid USDC version and potentially draining the contract's funds.

### Unsecured use of SafeERC20
- Location: contracts/asd/asdUSDC.sol : `withdraw` function
- Mechanism: The `withdraw` function uses the `SafeERC20` library to transfer ERC20 tokens. However, using `SafeERC20` can be problematic because it can be exploited by an attacker.
- Impact: An attacker can exploit this vulnerability by providing a maliciously encoded message and potentially draining the contract's funds.

### Missing event emission
- Location: contracts/asd/asdUSDC.sol : `withdraw` function
- Mechanism: The `withdraw` function does not emit an event when withdrawing tokens. This can make it difficult to track the contract's activity.
- Impact: An attacker can exploit this vulnerability by withdrawing tokens without anyone noticing.

Note: A more thorough audit would require testing the contracts and reviewing the code in more detail. This list is not exhaustive and is intended to provide a starting point for further review.
