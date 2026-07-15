// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

contract SafePool {
    uint256 public reserveETH;
    uint256 public reserveToken;
    mapping(address => uint256) public tokenBalances;
    
    // Fixed oracle price for safe version (simplified TWAP analogue)
    uint256 public twapPrice = 1e18; 

    constructor() payable {
        require(msg.value > 0);
        reserveETH = msg.value;
        reserveToken = msg.value;
    }

    function swapETHForToken() public payable {
        uint256 amountOut = (msg.value * reserveToken) / reserveETH;
        reserveETH += msg.value;
        reserveToken -= amountOut;
        tokenBalances[msg.sender] += amountOut;
    }

    function claimReward(uint256 tokenAmount) public {
        require(tokenBalances[msg.sender] >= tokenAmount, "Not enough tokens");
        tokenBalances[msg.sender] -= tokenAmount;

        // FIX: Uses a stored/TWAP price instead of the immediate spot reserves
        // There is no code path where an attacker can update twapPrice in this simplified contract.
        // Even if they could (in a real TWAP), it requires a block boundary to update.
        uint256 rewardETH = (tokenAmount * twapPrice) / 1e18;
        
        reserveToken += tokenAmount;
        reserveETH -= rewardETH;
        
        (bool success, ) = msg.sender.call{value: rewardETH}("");
        require(success, "ETH transfer failed");
    }
}
