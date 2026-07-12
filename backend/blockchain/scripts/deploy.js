import hre from "hardhat";
import fs from "fs";
import path from "path";
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

async function main() {
  const contractName = process.env.CONTRACT_NAME;
  if (!contractName) {
    console.error("CONTRACT_NAME environment variable is required.");
    process.exit(1);
  }

  try {
    console.log(`Deploying ${contractName}...`);
    // Ensure it's compiled
    await hre.run("compile");

    const ContractFactory = await hre.ethers.getContractFactory(contractName);
    const contract = await ContractFactory.deploy();
    
    // Wait for the deployment to finish
    await contract.waitForDeployment();
    const address = await contract.getAddress();

    console.log(`Contract deployed to: ${address}`);

    // Get test accounts and their balances for verification
    const signers = await hre.ethers.getSigners();
    console.log("Test accounts seeded:");
    for (let i = 0; i < Math.min(3, signers.length); i++) {
      const balance = await hre.ethers.provider.getBalance(signers[i].address);
      console.log(`- ${signers[i].address} (${hre.ethers.formatEther(balance)} ETH)`);
    }

    // Prepare JSON output
    const artifact = await hre.artifacts.readArtifact(contractName);
    const output = {
      success: true,
      address: address,
      abi: artifact.abi
    };

    const deploymentsDir = path.join(__dirname, "..", "deployments");
    if (!fs.existsSync(deploymentsDir)) {
      fs.mkdirSync(deploymentsDir, { recursive: true });
    }

    const outputPath = path.join(deploymentsDir, `${contractName}.json`);
    fs.writeFileSync(outputPath, JSON.stringify(output, null, 2));
    console.log(`Deployment state written to ${outputPath}`);
    
    process.exit(0);
  } catch (error) {
    console.error("Deployment failed:", error);
    process.exit(1);
  }
}

main();
