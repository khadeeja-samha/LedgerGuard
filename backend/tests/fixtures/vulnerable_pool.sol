// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

contract VulnerablePool {
    uint256 public reserveETH;
    uint256 public reserveToken;
    mapping(address => uint256) public tokenBalances;

    constructor() payable {
        require(msg.value > 0);
        reserveETH = msg.value;
        reserveToken = msg.value; // 1:1 initial ratio
    }

    // 1. Swap function to skew the reserves
    function swapETHForToken() public payable {
        uint256 amountOut = (msg.value * reserveToken) / reserveETH;
        reserveETH += msg.value;
        reserveToken -= amountOut;
        tokenBalances[msg.sender] += amountOut;
    }

    // 2. Vulnerable function that uses the spot reserves as an oracle to pay out ETH rewards
    function claimReward(uint256 tokenAmount) public {
        require(tokenBalances[msg.sender] >= tokenAmount, "Not enough tokens");
        tokenBalances[msg.sender] -= tokenAmount;

        // VULNERABILITY: Spot price used directly.
        // Attacker pumps reserveETH (making tokens "worth" more ETH), then claims reward.
        uint256 rewardETH = (tokenAmount * reserveETH) / reserveToken;
        
        reserveToken += tokenAmount; // Add tokens back to reserve
        reserveETH -= rewardETH;     // Remove ETH from reserve
        
        (bool success, ) = msg.sender.call{value: rewardETH}("");
        require(success, "ETH transfer failed");
    }
}