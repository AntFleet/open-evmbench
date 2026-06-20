# Audit: 2024-05-olas

 memory values,
        bytes[] memory calldatas,
        bytes32 descriptionHash
    ) public payable virtual override returns (uint256) {
        uint256 proposalId = hashProposal(targets, values, calldatas, descriptionHash);

        ProposalState status = state(proposalId);
        require(
            status == ProposalState.Succeeded || status == ProposalState.Queued,
            "Governor: proposal not successful"
        );
        _proposals[proposalId].executed = true;

        emit ProposalExecuted(proposalId);

        _beforeExecute(proposalId, targets, values, calldatas, descriptionHash);
        _execute(proposalId, targets, values, calldatas, descriptionHash);
        _afterExecute(proposalId, targets, values, calldatas, descriptionHash);

        return proposalId;
    }
```
And then `_execute` is overridden in `GovernorOLA` as:
```solidity
    function _execute(
        uint256 proposalId,
        address[] memory targets,
        uint256[] memory values,
        bytes[] memory calldatas,
        bytes32 descriptionHash
    ) internal override(Governor, GovernorTimelockControl)
    {
        super._execute(proposalId, targets, values, calldatas, descriptionHash);
    }
```
Which calls `GovernorTimelockControl._execute`:
```solidity
    function _execute(
        uint256, /* proposalId */
        address[] memory targets,
        uint256[] memory values,
        bytes[] memory calldatas,
        bytes32 descriptionHash
    ) internal virtual override {
        _timelock.executeBatch{value: msg.value}(targets, values, calldatas, 0, descriptionHash);
    }
```
Wait! Look at this!
In `GovernorCompatibilityBravo.execute(uint256 proposalId)`:
It calls `execute(...)` with `msg.value` not forwarded?
Wait! In Solidity, when you call a sibling public function on `this`, or when you call `execute` (which is a public function):
If you do:
```solidity
    function execute(uint256 proposalId) public payable virtual override {
        ProposalDetails storage details = _proposalDetails[proposalId];
        execute(
            details.targets,
            details.values,
            _encodeCalldata(details.signatures, details.calldatas),
            details.descriptionHash
        );
    }
```
Is `msg.value` forwarded to the internal/external `execute` call?
Ah! `execute(...)` is a public function of the SAME contract.
When a public function inside a contract calls another public function on `this` implicitly (without `this.execute(...)`), it is executed as an **internal** jump in Solidity.
So it is still the same transaction execution context.
Thus, `msg.value` is still available in the execution of `execute(targets, values, calldatas, descriptionHash)`.
And then `_execute` is called, which calls `_timelock.executeBatch{value: msg.value}`.
So `msg.value` is indeed forwarded correctly.

But wait!
What if there are multiple times we call `execute` with the same `proposalId`?
`_proposals[proposalId].executed` is set to `true` inside `Governor.execute`.
And in `Governor.state`:
```solidity
        if (proposal.executed) {
            return ProposalState.Executed;
        }
```
So calling it again will fail because `status` will be `Executed`, not `Succeeded` or `Queued`.
This is also safe.

---
Let's look at `OLA.sol`'s `changeMinter`.
```solidity
    function changeMinter(address newMinter) external {
        if (msg.sender != owner) {
            revert ManagerOnly(msg.sender, owner);
        }

        minter = newMinter;
        emit MinterUpdated(newMinter);
    }
```
Wait, is there any check that `newMinter != address(0)`?
No! `changeMinter` allows setting `minter` to `address(0)`.
Is it a problem? If the minter is set to `address(0)`, then no more tokens can be minted, which is a feature (renouncing minter).
But what about `changeOwner`?
```solidity
    function changeOwner(address newOwner) external {
        if (newOwner == address(0)) {
            revert ZeroAddress();
        }
        ...
```
It has `ZeroAddress()` check.

Let's look at `GuardCM.sol`'s `checkTransaction` again.
Is there any bypass of the Gnosis Safe guard in `GuardCM`?
Let's see:
```solidity
    function checkTransaction(
        address to,
        uint256,
        bytes memory data,
        Enum.Operation operation,
        uint256,
        uint256,
        uint256,
        address,
        address payable,
        bytes memory,
        address
    ) external {
```
The Gnosis Safe guard `checkTransaction` function is called *before* a Gnosis Safe transaction is executed.
If the guard reverts, the transaction reverts.
Let's see if an attacker can bypass the check.
If `paused == 1`:
- If `operation == Enum.Operation.DelegateCall`, it reverts with `NoDelegateCall()`.
- If `to == owner` (the timelock):
  - `data` is checked.
  - If `functionSig == SCHEDULE || functionSig == SCHEDULE_BATCH`:
    - It dec
