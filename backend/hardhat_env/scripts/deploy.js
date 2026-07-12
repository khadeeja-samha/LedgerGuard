import fs from 'fs';
import path from 'path';
import hre from 'hardhat';

async function main() {
  // Read artifacts to find the compiled contract name
  const artifactsPath = path.join(process.cwd(), 'artifacts', 'contracts');
  
  if (!fs.existsSync(artifactsPath)) {
    throw new Error('No artifacts found. Did compilation succeed?');
  }

  // Find the first .sol directory
  const files = fs.readdirSync(artifactsPath);
  const solDirName = files.find(f => f.endsWith('.sol'));
  if (!solDirName) {
    throw new Error('No .sol artifact directory found.');
  }

  const solDirPath = path.join(artifactsPath, solDirName);
  
  // Inside the .sol directory, find the JSON file that isn't a db file
  const artifactFiles = fs.readdirSync(solDirPath);
  const jsonFile = artifactFiles.find(f => f.endsWith('.json') && !f.endsWith('.dbg.json'));
  
  if (!jsonFile) {
    throw new Error('No contract artifact JSON found.');
  }

  const contractName = jsonFile.replace('.json', '');

  console.log(`Deploying ${contractName}...`);

  const ContractFactory = await hre.ethers.getContractFactory(contractName);
  const contract = await ContractFactory.deploy();

  await contract.waitForDeployment();
  const address = await contract.getAddress();

  console.log(`${contractName} deployed to ${address}`);

  // Read ABI
  const artifactData = JSON.parse(fs.readFileSync(path.join(solDirPath, jsonFile), 'utf8'));
  const abi = artifactData.abi;

  const output = {
    contractName,
    address,
    abi
  };

  fs.writeFileSync(path.join(process.cwd(), 'deployment.json'), JSON.stringify(output, null, 2));
  console.log('Deployment written to deployment.json');
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });
