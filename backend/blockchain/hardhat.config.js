import "@nomicfoundation/hardhat-toolbox";

/** @type import('hardhat/config').HardhatUserConfig */
export default {
  solidity: "0.8.24",
  networks: {
    localhost: {
      url: "http://127.0.0.1:8545"
    }
  },
  paths: {
    sources: process.env.HARDHAT_SOURCES || "./contracts",
    artifacts: process.env.HARDHAT_ARTIFACTS || "./artifacts",
    cache: process.env.HARDHAT_CACHE || "./cache"
  }
};
