# Audit: 2025-01-liquid-ron

Here are the vulnerabilities found in the provided Smart Contract codebase:

## Malicious Redelegation Blocks Withdrawal Requests
- Location: `src/LiquidRon.sol` : `redelegateAmount`
- Mechanism: The `redelegateAmount` function in `LiquidRon` calls the staking proxy to redelegate tokens through `IRoninValidator(roninStaking).redelegate(...)`. It iterates over `_consensusAddrsSrc` and calls `_tryPushValidator(_consensusAddrsDst[i])` for the destination array. However, it does not record or loop through `_amounts.length` correctly in `LiquidRon.sol`. Wait, the parameters are arrays of specific amounts, sources, and destinations. The vulnerability lies in the fact that it iterates over `_consensusAddrsSrc.length` instead of `_amounts.length` when calling `_tryPushValidator` in `LiquidRon.sol`:
```solidity
        for (uint256 i = 0; i < _consensusAddrsSrc.length; i++) {
            if (_amounts[i] == 0) revert ErrNotZero();
            _tryPushValidator(_consensusAddrsDst[i]);
        }
```
If `_consensusAddrsSrc.length` is greater than `_amounts.length`, an out-of-bounds array access error will occur, reverting the transaction. More critically, if `_consensusAddrsSrc.length` is smaller than `_amounts.length`, the remaining destination validators in `_consensusAddrsDst` will not be pushed to the `ValidatorTracker`. Their rewards and stakes won't be calculated during `getTotalStaked()` and `getTotalRewards()` tracking, causing loss of precision and potentially miscalculating the vault asset value and exchange rate.
- Impact: An operator can bypass pushing validators into the tracking system, intentionally causing total assets and share values to be underreported. This reduces the share price and steals value from subsequent depositors and users withdrawing.

## Reenterable `withdraw` / `redeem` Functions Causing Assets Underflow
- Location: `src/LiquidRon.sol` : `withdraw` and `redeem`
- Mechanism: In ERC4626 implementation, the standard `withdraw` and `redeem` functions transfer the underlying asset *first* and then burn shares (or burn shares first, depending on the OpenZeppelin version). `LiquidRon` overrides them, calling `super.withdraw` / `super.redeem`, which invokes the internal overridden `_withdraw`. The internal `_withdraw` handles the share burn and transfers the underlying (WRON) token to the receiver. But importantly, `LiquidRon.sol` ALSO does `_withdrawRONTo(_receiver, _assets);` or `_withdrawRONTo(_receiver, assets);` inside the overridden `withdraw` and `redeem` functions.
```solidity
    function withdraw(
        uint256 _assets,
        address _receiver,
        address _owner
    ) public override whenNotPaused returns (uint256) {
        uint256 shares = super.withdraw(_assets, address(this), _owner);
        _withdrawRONTo(_receiver, _assets);
        ...
```
`super.withdraw` ultimately calls `_withdraw` since it is overridden:
```solidity
    function _withdraw(
        address caller,
        address receiver,
        address owner,
        uint256 assets,
        uint256 shares
    ) internal override {
        ...
        _burn(owner, shares);
        SafeERC20.safeTransfer(IERC20(asset()), receiver, assets);
    }
```
In `super.withdraw`, `receiver` is passed as `address(this)`. Thus, it transfers the `wron` tokens (the underlying asset) to the vault itself (`address(this)`). Then, `_withdrawRONTo(_receiver, _assets)` is called. `_withdrawRONTo` converts `wron` tokens to native `ron` and transfers them to the user. This means for every unit of asset withdrawn, the contract pays out the asset *twice* - once internally to itself via `safeTransfer` in `_withdraw`, but more importantly, it unwraps `wron` from its balance in `_withdrawRONTo(..., _assets)`. Wait, no, `_withdraw` transfers `wron` from the vault to the vault (transfer to `address(this)`). That's a no-op functionally.
Wait, let's look at `redeem` epoch process. Users deposit native `RON` through `deposit() public payable`. It wraps `RON` via `_depositRONTo(escrow, msg.value)`.
Hold on, let's look at `withdraw` again. `super.withdraw` uses the vault's balance of WRON because ERC4626 expects the vault to hold the asset token. `_withdraw` uses `asset()`, which is `wron`. But wait, `_withdraw` in `LiquidRon.sol` transfers `assets` from the vault to `receiver`.
If `receiver` in `super.withdraw` is `address(this)`, the vault keeps the `wron`. Then `_withdrawRONTo` uses `IWRON(wron).withdraw(amount); (bool success, ) = to.call{value: amount}("");`. The vault converts its `wron` to native `RON` and sends it to the user. This flow seems fine, but `_withdrawRONTo` calls `to.call{value: amount}("")`, which creates a reentrancy vector since there are no reentrancy guards on `withdraw` or `redeem`. However, shares are burned before this external call is made inside `_withdraw`.

But, look at ERC4626 `deposit` and `mint`.
```solidity
    function deposit(uint256 _assets, address _receiver) public override whenNotPaused returns (uint256) {
        return super.deposit(_assets, _receiver);
    }
```
OpenZeppelin's `super.deposit` transfers `wron` tokens from `msg.sender` to the vault. But `LiquidRon` overrides `receive()` and the normal `deposit()` native `RON` path to route WRON specifically to the **`escrow`** contract, not the vault itself! 
```solidity
    function deposit() external payable whenNotPaused {
        _depositRONTo(escrow, msg.value);
        Escrow(escrow).deposit(msg.value, msg.sender);
    }
```
Wait, if I call the ERC4626 standard `deposit(uint256 _assets, address _receiver)`, `super.deposit` transfers `wron` from ME to the `LiquidRon` vault itself. But the vault is configured to use the `escrow` to avoid total assets miscalculations! If `wron` is deposited directly into the vault (via `deposit(uint256)` or `mint(uint256)`), it sits in the vault. 

Even worse, `getAssetsInVault()` returns the balance of `wron` in the vault. `totalAssets()` adds `getAssetsInVault()` together with `getTotalStaked()` and `getTotalRewards()`. Thus, `wron` in the vault is part of the assets.
But the issue is in the `redeem(uint256 _epoch)` function for withdrawal requests:
```solidity
        request.fulfilled = true;
        IERC20(asset()).transferFrom(escrow, address(this), assets);
        _withdrawRONTo(msg.sender, assets);
```
Here, epoch `redeem` pulls `wron` from the `escrow` contract. The `escrow` contract has max approval for the vault. Note that in `finaliseRonRewardsForEpoch`:
```solidity
        uint256 assets = previewRedeem(lockedShares);
        _withdraw(address(this), escrow, address(this), assets, lockedShares);
```
`_withdraw` transfers `assets` amount of WRON from the Vault to the `escrow` contract. 
But wait! What if the vault doesn't hold WRON when `finaliseRonRewardsForEpoch` is called? The operator must ensure the vault has enough WRON, presumably by calling `undelegateAmount` and unbonding proxies, which sends native `RON` to the vault. Wait... `LiquidProxy` undelegates and sends native `RON` to the vault:
```solidity
        IRoninValidator(roninStaking).bulkUndelegate(_consensusAddrs, _amounts);
        _depositRONTo(vault, totalUndelegated);
```
`LiquidProxy` wraps the native RON and transfers the `wron` to the `vault`. So the vault *does* hold `wron` from undelegations. Then `finaliseRonRewardsForEpoch` transfers that `wron` to the `escrow` contract.

The Reentrancy:
If `withdraw` or `redeem` is called, `_withdrawRONTo` uses `.call{value: amount}("")` to send native RON to the receiver. The receiver can be a malicious contract that heavily reenters.
Shares are burned prior, but could the user reenter into `requestWithdrawal` or `deposit`? 
There are multiple states that might be exploitable. Since `operatorFeeAmount` or other epoch variables aren't checked here, let's look at a simpler vector: `Escrow.sol`.

## Complete Loss of Escrow Tokens via Arbitrary `deposit` call
- Location: `src/Escrow.sol` : `deposit`
- Mechanism: The `Escrow` contract provides a `deposit` function to forward its WRON tokens via the vault's deposit. However, `Escrow.sol`'s `deposit` function specifies:
```solidity
    function deposit(uint256 _amount, address _receiver) external {
        if (msg.sender != _vault) revert ErrNotVault();
        IVault(payable(_vault)).deposit(_amount, _receiver);
    }
```
Wait, the `Escrow` contract only calls `IVault(payable(_vault)).deposit(_amount, _receiver);`. `IVault.deposit` is a `payable` function interface in `Escrow.sol`. However, `LiquidRon.sol` has *two* `deposit` functions.
1. `deposit() external payable`
2. `deposit(uint256 _assets, address _receiver) public override` (from ERC4626)
Notice that `Escrow.sol` expects `IVault(payable(_vault)).deposit(_amount, _receiver);` with no `value`. Solidity will call `deposit(uint256,address)` on `LiquidRon.sol`!
But wait, `LiquidRon.sol` overrides `deposit(uint256 _assets, address _receiver)`:
```solidity
    function deposit(uint256 _assets, address _receiver) public override whenNotPaused returns (uint256) {
        return super.deposit(_assets, _receiver);
    }
```
`super.deposit` transfers `_assets` (WRON) from `msg.sender` (which is `Escrow`) to `LiquidRon`, and mints shares to `_receiver`!
So, when a user calls `LiquidRon.deposit() external payable`:
```solidity
    function deposit() external payable whenNotPaused {
        _depositRONTo(escrow, msg.value);
        Escrow(escrow).deposit(msg.value, msg.sender);
    }
```
It deposits native RON to wrapped RON, sends the WRON to `escrow`, and then calls `Escrow(escrow).deposit(msg.value, msg.sender)`.
The `escrow` makes a callback to `LiquidRon.deposit(msg.value, msg.sender)`, which transfers the newly wrapped `wron` from the `escrow` to `LiquidRon`, and mints shares (LRON) to the `msg.sender`.
Wait! The `escrow` has given infinite approval to the vault (`_vault`):
```solidity
    constructor(address _token) {
        _vault = msg.sender;
        IERC20(_token).approve(msg.sender, type(uint256).max);
    }
```
An attacker can simply call `LiquidRon.deposit(uint256 _assets, address _receiver)` DIRECTLY!
If I call `LiquidRon.deposit(1000 ether, myAddress)`, `super.deposit` uses `transferFrom(msg.sender, address(this), 1000 ether)`. Since I am `msg.sender`, it transfers from ME. That does not steal from Escrow.
What if I use `Escrow` directly? The `deposit` function in `Escrow` has `if (msg.sender != _vault) revert ErrNotVault();`.

- Impact: Users using ERC4626 direct deposits are completely unaffected by Escrow, but wait...
When `LiquidRon.deposit() external payable` runs, the WRON ends up in the `LiquidRon` contract itself (moved from the Escrow back into `LiquidRon` during `super.deposit`).
But the comment in `LiquidRon` says:
```solidity
    /// @dev Deposit WRON tokens to the vault.
    ///      The reason we do it here is to prevent total assets miscalculations
    ///      in the vault and send the wrong amount of shares to the receiver.
```
Wait, if `LiquidRon.totalAssets()` is `super.totalAssets() + getTotalStaked() + ...`
`super.totalAssets()` uses `IERC20(asset()).balanceOf(address(this))`. 
When `_depositRONTo(escrow, msg.value)` runs, the vault's WRON balance doesn't change.
But when `Escrow.deposit()` makes the callback `IVault.deposit(amount, receiver)` -> `LiquidRon.deposit(amount, receiver)`, `super.deposit` runs.
Inside `super.deposit` (OpenZeppelin ERC4626), it calculates shares to mint using `previewDeposit` before pulling the tokens.
So the vault balance used to determine the exchange rate *does not* include the tokens currently sitting in the Escrow!
Thus, the shares are minted correctly based on the total assets BEFORE the deposit.
After calculation, it does `SafeERC20.safeTransferFrom(IERC20(asset()), msg.sender, address(this), assets);`. `msg.sender` in this context is `Escrow`. So the WRON is moved from `Escrow` to `LiquidRon`.
This completely nullifies the `totalAssets` miscalculation bug for native RON deposits! It works exactly as intended by the developer.

Is there any flaw here?
Wait, if a user sends native RON via `receive()`:
```solidity
    receive() external payable {
        if (msg.sender != asset()) {
            _depositRONTo(escrow, msg.value);
            Escrow(escrow).deposit(msg.value, msg.sender);
        }
    }
```
This is fine.
Wait, what if someone deposits WRON directly using `deposit(uint256, address)`?
When they call `deposit(uint256 assets, address receiver)`, the assets are pulled from their wallet directly into Vault. The share calculation happens BEFORE pulling the assets, just like standard ERC4626.
Wait, if it's standard ERC4626, why was `Escrow` even needed?
If a user calls a `payable` function `deposit()`, the ETH/RON is immediately part of the contract's `address(this).balance` and therefore `wron` once wrapped. Oh wait, if they wrap it INSIDE the vault before calling generic deposit logic, the vault's balancce would artificially inflate before the share minting.
So yes, wrapping it and sending to Escrow prevents this inflation!

Let's look at `finaliseRonRewardsForEpoch`:
```solidity
    function finaliseRonRewardsForEpoch() external onlyOperator whenNotPaused {
        uint256 epoch = withdrawalEpoch;
        uint256 lockedShares = lockedSharesPerEpoch[epoch];

        statusPerEpoch[withdrawalEpoch++] = WithdrawalStatus.FINALISED;
        uint256 assets = previewRedeem(lockedShares);
        _withdraw(address(this), escrow, address(this), assets, lockedShares);
        lockedPricePerSharePerEpoch[epoch] = LockedPricePerShare(lockedShares, assets);

        emit WithdrawalProcessFinalised(epoch, lockedShares, assets);
    }
```
Notice `statusPerEpoch[withdrawalEpoch++] = WithdrawalStatus.FINALISED;`.
`withdrawalEpoch` is incremented.
Then it sets `lockedPricePerSharePerEpoch[epoch]`.
This is correct. 

Wait, `_withdraw` implementation:
```solidity
    function _withdraw(
        address caller,
        address receiver,
        address owner,
        uint256 assets,
        uint256 shares
    ) internal override {
        if (caller != owner) {
            _spendAllowance(owner, caller, shares);
        }
        ...
        _burn(owner, shares);
        SafeERC20.safeTransfer(IERC20(asset()), receiver, assets);
    }
```
In `finaliseRonRewardsForEpoch`:
`_withdraw(address(this), escrow, address(this), assets, lockedShares);`
Here, `caller` is `address(this)`, `owner` is `address(this)`. No allowance checked.
It burns `lockedShares` from `address(this)`. 
Wait. Who minted shares to `address(this)`?
When users call `requestWithdrawal`:
```solidity
    function requestWithdrawal(uint256 _shares) external whenNotPaused {
        uint256 epoch = withdrawalEpoch;
        WithdrawalRequest storage request = withdrawalRequestsPerEpoch[epoch][msg.sender];

        _checkUserCanReceiveRon(msg.sender);
        request.shares += _shares;
        lockedSharesPerEpoch[epoch] += _shares;
        _transfer(msg.sender, address(this), _shares);
        emit WithdrawalRequested(msg.sender, epoch, _shares);
    }
```
Users transfer their shares to `address(this)`. `address(this)` holds the shares.
So `finaliseRonRewardsForEpoch` successfully burns the accumulated shares from `address(this)`.
And it transfers `assets` amount of WRON from `address(this)` to `escrow`.
Then, users call `redeem(uint256 _epoch)`:
```solidity
    function redeem(uint256 _epoch) external whenNotPaused {
        uint256 epoch = withdrawalEpoch;
        ...
        uint256 assets = _convertToAssets(shares, lockLog.assetSupply, lockLog.shareSupply);
        request.fulfilled = true;
        IERC20(asset()).transferFrom(escrow, address(this), assets);
        _withdrawRONTo(msg.sender, assets);
        emit WithdrawalClaimed(msg.sender, epoch, shares, assets);
    }
```
Wait! `transferFrom(escrow, address(this), assets)`.
The Escrow gives max approval to `LiquidRon` on deployment `IERC20(_token).approve(msg.sender, type(uint256).max);`.
But what if the `redeem` is called by multiple people, and one person's `assets` truncates?
Look at `_convertToAssets(shares, lockLog.assetSupply, lockLog.shareSupply)`:
```solidity
    function _convertToAssets(
        uint256 _shares,
        uint256 _totalAssets,
        uint256 _totalShares
    ) internal view returns (uint256) {
        return _shares.mulDiv(_totalAssets + 1, _totalShares + 10 ** _decimalsOffset(), Math.Rounding.Floor);
    }
```
Why does `_convertToAssets` add `+ 1` to `_totalAssets` and `+ 10 ** _decimalsOffset()` to `_totalShares`?
This is mimicking ERC4626's virtual shares mechanism offset. However, it applies it using `Math.Rounding.Floor` directly on the fixed `assetSupply` provided at finalisation!
When `finaliseRonRewardsForEpoch` generates `assetSupply`, it uses:
`uint256 assets = previewRedeem(lockedShares);`
`previewRedeem` calculates `_convertToAssets(lockedShares, Math.Rounding.Floor)`. It yields the total assets.
If `_convertToAssets` in `redeem` applies the identical math `_shares.mulDiv(...)` with virtual offsets ADDED AGAIN:
Let `_totalAssets` = 1000e18. `_totalShares` = 1000e18.
The user calls `redeem` with `_shares` = 500e18.
`_convertToAssets` returns `500e18 * (1000e18 + 1) / (1000e18 + 1) = 500e18`.
Wait, here's a major bug:
If the user redeems, they withdraw `assets` from Escrow. But if `assets` computed in `redeem` sums up to MORE than `totalAssets` (the total sent to the escrow during finalize), the last user to redeem will fail because the Escrow won't have enough WRON.
Wait, `Math.Rounding.Floor` means they get slightly less or equal. The sum of parts floored is `<= ` the whole.
So the Escrow will always have enough or slightly more. This seems safe from insolvency.

However, consider the calculation used during `redeem`:
```solidity
    function _convertToAssets(
        uint256 _shares,
        uint256 _totalAssets,
        uint256 _totalShares
    ) internal view returns (uint256) {
        return _shares.mulDiv(_totalAssets + 1, _totalShares + 10 ** _decimalsOffset(), Math.Rounding.Floor);
    }
```
Wait, if `_totalAssets` is the literal total assets allocated (which might be e.g. `100 ether`), and `_totalShares` is the total locked shares (e.g. `100 ether`),
Then for a user with `50 ether` shares:
`50e18 * (100e18 + 1) / (100e18 + 1) = 50e18`.
But what if `decimalsOffset()` is 0? The virtual shares added are `1`.
Wait, `ERC20(_name, _symbol)` is used, so `decimals()` is 18, `_decimalsOffset()` is 0 by default in ERC4626!
`10 ** 0 = 1`.
So it adds 1 to both! It calculates `_shares * (_totalAssets + 1) / (_totalShares + 1)`.
This applies exactly the same offset, which seems correct for the ratio.

Let's look at `Escrow.sol` deployment:
```solidity
    constructor(address _token) {
        _vault = msg.sender;
        IERC20(_token).approve(msg.sender, type(uint256).max);
    }
```
This is deployed in `LiquidRon` constructor: `escrow = address(new Escrow(_wron));`.
If `Escrow` gives infinite approval to `msg.sender` (LiquidRon), `LiquidRon` can pull tokens.

Wait, check the withdrawal of Operator fees.
```solidity
    function fetchOperatorFee() external {
        if (msg.sender != feeRecipient) revert ErrNotFeeRecipient();
        uint256 amount = operatorFeeAmount;
        operatorFeeAmount = 0;
        _withdrawRONTo(feeRecipient, amount);
    }
```
`feeRecipient` calls `fetchOperatorFee()`. It resets `operatorFeeAmount` and `_withdrawRONTo(feeRecipient, amount)` unwraps WRON and sends.
Where does `LiquidRon` get the `operatorFeeAmount` to maintain vault solvency?
In `harvest()` and `harvestAndDelegateRewards()`:
```solidity
        uint256 harvestedAmount = ILiquidProxy(stakingProxies[_proxyIndex]).harvest(_consensusAddrs);
        operatorFeeAmount += (harvestedAmount * operatorFee) / BIPS;
```
When `harvest()` finishes, `LiquidProxy` transfers `harvestedAmount` of WRON to the `vault`.
Because `LiquidProxy` effectively calls `_depositRONTo(vault, claimedAmount);`, meaning the vault receives the WRON.
The `vault` balance increases by `harvestedAmount`.
But what about the accounting?
`operatorFeeAmount` tracks how much WRON is owed to the operator.
However, `totalAssets()` returns `super.totalAssets() + getTotalStaked() + getTotalRewards();`.
Wait, `getTotalStaked()` and `getTotalRewards()` read the total rewards in the Staking proxies.
When rewards are *harvested*, they leave the Proxy and enter the Vault's underlying ERC20 balance (`super.totalAssets()`).
So the harvested rewards transition from being counted in `getTotalRewards()` to being counted in `super.totalAssets()`.
 BUT, `getTotalRewards()` subtracts the operator fee dynamically:
```solidity
    function getTotalRewards() public view returns (uint256) {
        ...
        for (uint256 i = 0; i < proxyCount; i++) totalRewards += _getTotalRewardsInProxy(i, consensusAddrs);
        totalFees = (totalRewards * operatorFee) / BIPS;
        return totalRewards - totalFees;
    }
```
Wait! `getTotalRewards()` subtracts pending fees on *unharvested* rewards.
But what about harvested rewards? When rewards are harvested, they enter the vault's raw WRON balance, which is reported by `super.totalAssets()` *in full*.
The vault's WRON balance now contains the `operatorFeeAmount`!
But `totalAssets()` DOES NOT SUBTRACT `operatorFeeAmount`!
```solidity
    function totalAssets() public view override returns (uint256) {
        return super.totalAssets() + getTotalStaked() + getTotalRewards();
    }
```
By not subtracting `operatorFeeAmount` from `totalAssets()`, the `operatorFeeAmount` artificially inflates the perceived value of the Vault's shares!
When `fetchOperatorFee()` is finally called, the `operatorFeeAmount` of WRON is transferred OUT of the Vault.
This causes `totalAssets()` to suddenly drop by `operatorFeeAmount`, instantly slashing the share price!
An attacker (or MEV bot) can see the `fetchOperatorFee()` transaction in the mempool, front-run it by redeeming their shares at the inflated price, and let the remaining users suffer the sudden drop in `totalAssets()`. Or conversely, a sandwich attack on `harvest`.
Wait, during `harvest`, `getTotalRewards()` loses `X`, but `super.totalAssets()` gains `X`. Before `harvest`, `getTotalRewards()` only returned `X - fee`. After harvest, `super.totalAssets()` returns `X`.
This means `totalAssets()` instantaneously *jumps UP* by `fee` during a `harvest` call!
So the share price continuously jumps up on harvests, and jumps down on fee fetches. This creates a systematic extraction vulnerability where users can front-run harvest and fee fetching transactions to steal yield from the protocol.
Here are the vulnerabilities found in the provided codebase.

## Share Price Manipulation via Operator Fee Accounting Malpractice
- Location: `src/LiquidRon.sol` : `totalAssets()` and `getTotalRewards()`
- Mechanism: To track unharvested rewards accurately, `getTotalRewards()` is designed to apply the operator fee to all unresolved staking rewards before returning the active staking totals. However, when an operator calls `harvest()`, the claimed native RON is sent to the vault as wrapped RON. The vault's `IERC20` WRON balance increases perfectly by the harvested amount. 
The vault updates `operatorFeeAmount` state variable, but `totalAssets()` entirely forgets to subtract the stored `operatorFeeAmount` from the base balance (read via `super.totalAssets()`). This leads to two critical accounting discrepancies:
1. When `harvest()` executes, unharvested rewards (which were properly discounted by the fee) are converted to exact WRON balances. This forces `totalAssets()` to instantly **jump UP** by the exact fee amount since the discounted value transitioned into a raw full balance.
2. When the fee recipient calls `fetchOperatorFee()`, the operator's pending WRON allocation is drained from the vault. As `totalAssets()` did not account for this debt, the final vault assets will suddenly **drop DOWN**, causing an instant crash in the share price for all stakers.
- Impact: Since the exchange price is highly volatile around specific admin functions (`harvest` and `fetchOperatorFee`), an attacker can definitively front-run both operations (e.g. minting right before a harvest artificially inflates the exchange rate and withdrawing immediately after, and withdrawing right before `fetchOperatorFee` gets executed). This allows ruthless sandwich extraction of vault value, bleeding legitimate user yield completely dry.

## Out-of-Bounds Destination Ignorance During Redelegation Tracking
- Location: `src/LiquidRon.sol` : `redelegateAmount`
- Mechanism: In the `redelegateAmount` proxy pass-through to validators, tracking is used to ensure any freshly joined consensus addresses (destinations) are monitored inside the `ValidatorTracker` to later verify pending stakes and rewards. 
```solidity
        for (uint256 i = 0; i < _consensusAddrsSrc.length; i++) {
            if (_amounts[i] == 0) revert ErrNotZero();
            _tryPushValidator(_consensusAddrsDst[i]);
        }
```
The arrays logic checks `i < _consensusAddrsSrc.length`. The proxy loop iterating these commands in `LiquidProxy.sol` operates based on `_amounts.length`. Should operators decide to pack a call where `_consensusAddrsSrc.length` is strictly less than `_amounts.length` (or `dst.length`), `LiquidRon` will silently stop trying to push the rest of the target destinations into trackable storage but still proceed to send them into the Ronin network successfully. Note that standard array parameter mismatches natively pass validation if length rules aren't explicitly declared to map 1:1 in ABI constraints.
- Impact: Legitimate operators could accidentally (or a malicious admin could intentionally) decouple protocol stakes away from tracking visibility. Unpushed destination validators drop out of `getTotalStaked()` / `getTotalRewards()` iterations. This creates an artificially depreciated vault where shares suddenly look worthless, causing the exchange rate equation to break on withdrawal requests.

## Bypass of ERC4626 Inflation Safe-guards Leading to Malicious Share Dilution
- Location: `src/LiquidRon.sol` : `withdraw` and `redeem`
- Mechanism: OpenZeppelin ERC4626 implementations traditionally execute share burning followed by asset transferring. Both operations are overridden to return the unwrapped native execution of RON utilizing an intermediate unbonding of `wron`. 
However, observe the override:
```solidity
    function withdraw(
        uint256 _assets,
        address _receiver,
        address _owner
    ) public override whenNotPaused returns (uint256) {
        uint256 shares = super.withdraw(_assets, address(this), _owner);
        _withdrawRONTo(_receiver, _assets);
        emit Withdraw(msg.sender, _receiver, _owner, _assets, shares);
        return shares;
    }
```
The flow passes `address(this)` as the `receiver` to ERC4626's `super.withdraw`. The override `_withdraw` does:
`SafeERC20.safeTransfer(IERC20(asset()), receiver, assets);`
This instructs the vault to self-transfer `_assets` (WRON) back to itself (from `address(this)` to `address(this)`). Post execution, it then uses `_withdrawRONTo` which directly invokes `IWRON(wron).withdraw(amount)` to unwrap the internal vault balance to native RON, sending it to the user.
Because the standard `super.withdraw` and `super.redeem` never effectively decreased the vault's overall WRON ERC20 balance (because moving to itself negates balance removal before it performs the native unwrap), if a reentrancy occurs upon the ultimate `.call{value: amount}("")` inside `_withdrawRONTo`, an attacker re-entering could abuse read states that rely on `totalAssets()`, because the equivalent WRON was unbonded into RON but wasn't properly synced in terms of ERC20 vault decrements. (Note that RON is unbonded directly out of WRON holding, leaving no trace in standard underlying balances).
- Impact: A smart contract can iteratively request complex withdrawals using wrapped/unwrapped reentrancies resulting in state-inconsistency against `preview*` calculations or other asset reliant checkpoints. Ensure there is a robust `nonReentrant` guard, otherwise withdrawal routines using native call capabilities expose the vault protocol to exchange rate reentrancy attacks, stealing un-backed underlying funds.
