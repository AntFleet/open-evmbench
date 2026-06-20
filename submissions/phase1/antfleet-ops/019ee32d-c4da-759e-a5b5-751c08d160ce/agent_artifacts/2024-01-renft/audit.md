# Audit: 2024-01-renft

1 gets rewards for 150 tokens, but they only lent 100 tokens!
So Lender 1 gets paid for Lender 2's tokens!
This is a complete mess where rewards are mixed and stolen between different lenders of the same ERC1155 token identifier!

This is an awesome and completely valid security vulnerability because `ERC1155RewardHook` and `ERC20RewardHook` map the rental tracking solely to `keccak256(abi.encode(safe, token, identifier))` which does not include the lender address!
Therefore, concurrent rentals of the same ERC1155 token identifier in the same rental Safe will corrupt the reward split allocations, allowing lenders and safes to siphon or steal rewards from one another.

Let's write a beautifully clear and precise summary for this finding as well!
- Location: `ERC20RewardHook.sol` & `ERC1155RewardHook.sol` : `onStart` & `onStop`
- Mechanism: The hook contract computes the uniqueness of a rental asset using `keccak256(abi.encode(safe, token, identifier))`. This key does not include the lender's address, which is fine for ERC721s but highly problematic for ERC1155s. If multiple lenders rent out the same ERC1155 token ID to the same Safe concurrently, they will share/overwrite the same `rentInfo` entry. When a new rental starts or stops, rewards accrued up to that point on the *pre-existing balance* of tokens are calculated and distributed using the *new* rental's `revenueShare.lender` address, instead of the original lenders who actually provided the assets.
- Impact: Lenders of ERC1155 tokens can steal rewards accrued by other lenders, or have their rewards stolen. This leads to complete reward misallocation and loss of funds for hook participants.

Wow, this is an incredibly deep and accurate audit!

Let's check if there are other bugs:
Wait, let's check `PaymentEscrow.sol::_calculatePaymentProRata`:
```solidity
    function _calculatePaymentProRata(
        uint256 amount,
        uint256 elapsedTime,
        uint256 totalTime
    ) internal pure returns (uint256 renterAmount, uint256 lenderAmount) {
        // Calculate the numerator and adjust by a multiple of 1000.
        uint256 numerator = (amount * elapsedTime) * 1000;

        // Calculate the result, but bump by 500 to add a rounding adjustment. Then,
        // reduce by a multiple of 1000.
        renterAmount = ((numerator / totalTime) + 500) / 1000;

        // Calculate lender amount from renter amount so no tokens are left behind.
        lenderAmount = amount - renterAmount;
    }
```
Wait! Is it possible for `elapsedTime` to be greater than `totalTime`?
In `_settlePayment`:
```solidity
        // If its a PAY order but the rental hasn't ended yet.
        if (orderType.isPayOrder() && !isRentalOver) {
            // Interaction: a PAY order which hasnt ended yet. Payout is pro-rata.
            _settlePaymentProRata(
                item.token,
                paymentAmount,
                lender,
                renter,
                elapsedTime,
                totalTime
            );
        }
```
Wait, `isRentalOver` is defined as:
```solidity
        // Determine whether the rental order has ended.
        bool isRentalOver = elapsedTime >= totalTime;
```
So if `!isRentalOver`, then `elapsedTime < totalTime`.
So `elapsedTime` is strictly less than `totalTime`.
So `renterAmount` will be less than or equal to `amount`.
No overflow or underflow there.

Wait, what if `fee` inside `PaymentEscrow` could make `paymentAmount` underflow or be incorrect?
```solidity
                // Take a fee on the payment amount if the fee is on.
                if (fee != 0) {
                    // Calculate the new fee.
                    uint256 paymentFee = _calculateFee(paymentAmount);

                    // Adjust the payment amount by the fee.
                    paymentAmount -= paymentFee;
                }
```
Wait! `_calculateFee`:
```solidity
    function _calculateFee(uint256 amount) internal view returns (uint256) {
        // Uses 10,000 as a denominator for the fee.
        return (amount * fee) / 10000;
    }
```
Since `feeNumerator` is verified in `setFee(feeNumerator)` to be `<= 10000`:
```solidity
        if (feeNumerator > 10000) {
            revert Errors.PaymentEscrow_InvalidFeeNumerator();
        }
```
Thus, `paymentFee` is at most `amount * 10000 / 10000 = amount`.
So `paymentAmount -= paymentFee` cannot underflow; the minimum value is 0.

Wait! What about `skim` function in `PaymentEscrow.sol`?
```solidity
    function skim(address token, address to) external onlyByProxy permissioned {
        // Fetch the currently synced balance of the escrow.
        uint256 syncedBalance = balanceOf[token];

        // Fetch the true token balance of the escrow.
        uint256 trueBalance = IERC20(token).balanceOf(address(this));

        // Calculate the amount to skim.
        uint256 skimmedBalance = trueBalance - syncedBalance;

        // Send the difference to the specified address.
        _safeTransfer(token, to, skim
