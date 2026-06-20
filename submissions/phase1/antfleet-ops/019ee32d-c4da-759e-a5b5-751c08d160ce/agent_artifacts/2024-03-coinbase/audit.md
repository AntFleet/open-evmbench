# Audit: 2024-03-coinbase

 ERC20s? There are no specific deposit functions for ERC20s, but anyone can transfer ERC20s to the contract address.
So this seems like an intended feature.

Wait!
Let's look at `withdraw` and `postOp` interaction.
What if `withdraw` is called *during* the execution of a `UserOperation` that is sponsored by `MagicSpend`?
Wait, if a `UserOperation` is sponsored by `MagicSpend` (meaning `MagicSpend` is the paymaster):
During `validatePaymasterUserOp`, `_withdrawableETH[userOp.sender]` is increased by `withdrawAmount - maxCost`.
During the execution of the `UserOperation` (i.e. inside the wallet's execution phase), the wallet can call `MagicSpend.withdrawGasExcess()`.
Let's look at `withdrawGasExcess()`:
```solidity
    function withdrawGasExcess() external {
        uint256 amount = _withdrawableETH[msg.sender];
        // we could allow 0 value transfers, but prefer to be explicit
        if (amount == 0) revert NoExcess();

        delete _withdrawableETH[msg.sender];
        _withdraw(address(0), msg.sender, amount);
    }
```
This is fine, it withdraws the excess and sets `_withdrawableETH[msg.sender]` to 0.
Then in `postOp`:
```solidity
        // Compute the total remaining funds available for the user accout.
        // NOTE: Take into account the user operation gas that was not consummed.
        uint256 withdrawable = _withdrawableETH[account] + (maxGasCost - actualGasCost);

        // Send the all remaining funds to the user accout.
        delete _withdrawableETH[account];
```
This correctly transfers only the remaining unconsumed gas `maxGasCost - actualGasCost` to the user. This is perfectly correct.

But wait!
What if the user's `UserOperation` execution calls `MagicSpend.withdraw(withdrawRequest)`?
Can they do that?
They have a signed `withdrawRequest`.
If they call `withdraw(withdrawRequest)` during execution:
`_validateRequest` will mark the nonce as used.
It will call `_withdraw(asset, msg.sender, amount)`.
Wait!
Could this `withdrawRequest` be the EXACT same `withdrawRequest` that was used for the paymaster?
Let's check!
In `validatePaymasterUserOp`, the paymaster extracts `withdrawRequest` from `userOp.paymasterAndData[20:]`.
And it calls `_validateRequest(userOp.sender, withdrawRequest)`.
This marks the nonce of `withdrawRequest` as USED!
So if the user tries to call `withdraw(withdrawRequest)` *again* during execution, it will revert with `InvalidNonce` because the nonce was already marked as used during `validatePaymasterUserOp`!
This is correct.

But wait!
What if they try to do it the other way around?
What if the user first calls `withdraw(withdrawRequest)` directly in a standard transaction (or inside another userOp).
Then the nonce is marked as used.
Then they try to use the same `withdrawRequest` as a paymaster userOp?
During `validatePaymasterUserOp`, the contract calls `_validateRequest`.
Since the nonce was already marked as used, `_validateRequest` reverts with `InvalidNonce`.
Since `_validateRequest` reverts, `validatePaymasterUserOp` reverts.
This is also correct!

But wait, is there an issue with `postOp` and `actualGasCost`?
In `postOp`:
```solidity
    function postOp(IPaymaster.PostOpMode mode, bytes calldata context, uint256 actualGasCost)
        external
        onlyEntryPoint
    {
        // `PostOpMode.postOpReverted` should be impossible.
        // Only possible cause would be if this contract does not own enough ETH to transfer
        // but this is checked at the validation step.
        assert(mode != PostOpMode.postOpReverted);

        (uint256 maxGasCost, address account) = abi.decode(context, (uint256, address));

        // Compute the total remaining funds available for the user accout.
        // NOTE: Take into account the user operation gas that was not consummed.
        uint256 withdrawable = _withdrawableETH[account] + (maxGasCost - actualGasCost);
```
Wait!
What if `actualGasCost > maxGasCost`?
In ERC-4337, is it possible that `actualGasCost > maxGasCost`?
No, the EntryPoint guarantees that the `actualGasCost` is at most `maxGasCost` (which is the maximum gas cost calculated during validation based on `maxFeePerGas` and gas limits).
But wait!
What if `actualGasCost` is slightly more under some extreme circumstances? No, EntryPoint ensures `actualGasCost <= maxGasCost`.
But wait, is there any possibility of underflow?
`maxGasCost - actualGasCost` is safe because `actualGasCost <= maxGasCost`.
But since this is Solidity 0.8.23, an underflow would revert anyway.

Wait, what if `_withdrawableETH[account]` is not set properly or undergoes some overflow?
Since it uses `+=` in `validatePaymasterUserOp`:
`_withdrawableETH[userOp.sender] += withdrawAmount - maxCost;`
And this is in Solidity 0.8.23, so overflows are checked.

Let's look at `CoinbaseSmartWalletFactory.sol` and the stuck funds issue.
Let's double-check the code of `CoinbaseSmartWalletFactory.sol`:
```solidity
    function
