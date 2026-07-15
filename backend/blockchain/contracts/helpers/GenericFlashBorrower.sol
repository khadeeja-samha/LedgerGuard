// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

contract GenericFlashBorrower {
    address public target;
    bytes public attackPayload;
    
    function setup(address _target, bytes memory _attackPayload) external {
        target = _target;
        attackPayload = _attackPayload;
    }
    
    function executeAttack() external payable {
        (bool success, ) = target.call{value: msg.value}(attackPayload);
        require(success, "Attack call failed");
    }
    
    receive() external payable {}
}
