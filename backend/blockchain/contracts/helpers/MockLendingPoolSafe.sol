// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

interface IFlashLoanReceiver {
    function executeOperation(uint256 amount, uint256 fee, bytes calldata data) external;
}

contract MockLendingPoolSafe {
    uint256 public reserveToken = 10000;
    mapping(address => uint256) public tokenBalances;
    uint256 public oraclePrice = 10000; // Owner-settable or fixed price feed

    // FIX: Using an external/fixed oracle price instead of the internal reserve balance
    // This prevents price manipulation during a flash loan because oraclePrice does not change.
    function getPrice() public view returns (uint256) {
        return oraclePrice;
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
        uint256 requiredCollateral = (borrowAmount * getPrice()) / 100;
        require(msg.value >= requiredCollateral, "Insufficient collateral");
        tokenBalances[msg.sender] += borrowAmount;
        reserveToken -= borrowAmount;
    }
}
