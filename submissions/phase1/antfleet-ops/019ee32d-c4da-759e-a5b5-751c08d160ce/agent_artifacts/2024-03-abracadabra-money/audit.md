# Audit: 2024-03-abracadabra-money

) Owned(owner≤) {
        implementation = this;
...
```
Since it is immutable, for any clone, `implementation` will point to the deployed implementation contract address!
And `BlastMagicLP(address(implementation)).operators(msg.sender)` checks the implementation's operators mapping.
And `msg.sender != implementation.owner()` checks the implementation's owner.
Wait, does this mean clone operators are managed globally on the implementation contract?
Yes, this is an intentional design choice, so implementation owner/operators can claim yields for all clones at once.

Wait, let's look at `BlastOnboarding.sol:deposit()`:
```solidity
    function deposit(address token, uint256 amount, bool lock_) external whenNotPaused onlyState(State.Opened) onlySupportedTokens(token) {
        token.safeTransferFrom(msg.sender, address(this), amount);

        if (lock_) {
            totals[token].locked += amount;
            balances[msg.sender][token].locked += amount;
        } else {
            totals[token].unlocked += amount;
            balances[msg.sender][token].unlocked += amount;
        }

        totals[token].total += amount;

        if (caps[token] > 0 && totals[token].total > caps[token]) {
            revert ErrCapReached();
        }

        balances[msg.sender][token].total += amount;

        emit LogDeposit(msg.sender, token, amount, lock_);
    }
```
Wait!
Is there an issue with `caps[token]` check?
```solidity
        if (caps[token] > 0 && totals[token].total > caps[token]) {
            revert ErrCapReached();
        }
```
Yes, if `totals[token].total` exceeds `caps[token]`, it reverts, enforcing the cap. This is correct.

What about `BlastOnboarding.sol:lock()`?
```solidity
    function lock(address token, uint256 amount) external whenNotPaused onlyState(State.Opened) onlySupportedTokens(token) {
        balances[msg.sender][token].unlocked -= amount;
        balances[msg.sender][token].locked += amount;
        totals[token].unlocked -= amount;
        totals[token].locked += amount;

        emit LogLock(msg.sender, token, amount);
    }
```
No major issue here.

Let's read `oracles/aggregators/MagicLpAggregator.sol` again.
Is it possible to deploy `MagicLpAggregator`?
Yes, it is in `src/oracles/aggregators/MagicLpAggregator.sol`.
Wait! Is `_getReserves()` virtual?
```solidity
    function _getReserves() internal view virtual returns (uint256, uint256) {
        (uint256 baseReserve, uint256 quoteReserve) = pair.getReserves();
    }
```
Yes, it is virtual, but wait, does `MagicLpAggregator` have any sub-contracts that override `_getReserves()`?
Let's search the provided codebase.
No, there is no other contract in the codebase that inherits from `MagicLpAggregator`.
Even if there was, `MagicLpAggregator` itself should be correct on its own.
Since there is no return statement in the base implementation `_getReserves()`, any deployment of `MagicLpAggregator` that does not override `_getReserves()` (or uses it directly) will ALWAYS return 0 for reserves, and thus the latest answer will ALWAYS be 0!
This is a fatal floor in the oracle's core pricing logic!

Let's verify how `latestAnswer()` is calculated:
```solidity
    function latestAnswer() public view override returns (int256) {
        uint256 baseAnswerNomalized = uint256(baseOracle.latestAnswer()) * (10 ** (WAD - baseOracle.decimals()));
        uint256 quoteAnswerNormalized = uint256(quoteOracle.latestAnswer()) * (10 ** (WAD - quoteOracle.decimals()));
        uint256 minAnswer = baseAnswerNomalized < quoteAnswerNormalized ? baseAnswerNomalized : quoteAnswerNormalized;

        (uint256 baseReserve, uint256 quoteReserve) = _getReserves();
        baseReserve = baseReserve * (10 ** (WAD - baseDecimals));
        quoteReserve = quoteReserve * (10 ** (WAD - quoteDecimals));
        return int256(minAnswer * (baseReserve + quoteReserve) / pair.totalSupply());
    }
```
If `baseReserve = 0` and `quoteReserve = 0` due to `_getReserves()` not returning anything, then:
`minAnswer * (0 + 0) / pair.totalSupply()` = 0.
So `latestAnswer` always returns 0.
This is an outstanding finding!

Let's look at `LockingMultiRewards.sol:notifyRewardAmount` spike / manipulation again.
Is there an active vulnerability where anyone can profit?
Normally, to profit from a high reward rate spike, the user must stay in the pool.
Wait, if they deposit `unlocked` staking tokens, they can withdraw them immediately without any locking period!
Is there any withdrawal restriction in `LockingMultiRewards`?
Let's check `withdraw`:
```solidity
    function withdraw(uint256 amount) public virtual {
        if (amount == 0) {
            revert ErrZeroAmount();
        }

        _updateRewardsForUser(msg.sender);

        _balances[msg.sender].unlocked -= amount;
        unlockedSupply -= amount;

        
