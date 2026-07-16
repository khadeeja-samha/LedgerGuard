// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

interface IFlashLoanReceiver {
    function executeOperation(uint256 amount, uint256 fee, bytes calldata data) external;
}

contract MockLendingPoolVulnerable {
    uint256 public reserveToken = 10000;
    mapping(address => uint256) public tokenBalances;

    // VULNERABILITY: Spot price calculated directly from internal reserves (manipulable)
    function getPrice() public view returns (uint256) {
        return reserveToken;
    }

    function flashLoan(uint256 amount, bytes calldata data) external {
        uint256 fee = 10;
        tokenBalances[msg.sender] += amount;
        reserveToken -= amount;

        IFlashLoanReceiver(msg.sender).executeOperation(amount, fee, data);

        require(tokenBalances[msg.sender] >= amount + fee, "Flash loan not repaid");
        tokenBalances[msg.sender] -= (amount + fee);
        reserveToken += (amount + fee);
    }

    function borrowAgainstCollateral(uint256 borrowAmount) external payable {
        // Collateral required is determined by the manipulable getPrice()
        uint256 requiredCollateral = (borrowAmount * getPrice()) / 100;
        require(msg.value >= requiredCollateral, "Insufficient collateral");
        tokenBalances[msg.sender] += borrowAmount;
        reserveToken -= borrowAmount;
    }
}