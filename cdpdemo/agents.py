import os
import json

from decimal import Decimal
from typing import Union

from cdp.errors import UnsupportedAssetError
from cdp import Cdp, Wallet
from openai import OpenAI
from swarm import Agent
from web3 import Web3
from web3.exceptions import ContractLogicError
from farcaster_utils import FarcasterBot
from graph_utils import DaohausGraphData
from prompt_helpers import instructions

# Load the ENS registrar and resolver ABIs
with open("abis/registrar_abi.json", "r") as abi_file:
    registrar_abi = json.load(abi_file)

with open("abis/baal_abi.json", "r") as abi_file:
    baal_abi = json.load(abi_file)

with open("abis/yeet24_hos_summoner_abi.json", "r") as abi_file:
    yeet24_hos_summoner_abi = json.load(abi_file)

with open("abis/gnosis_multisend_abi.json", "r") as abi_file:
    gnosis_multisend_abi = json.load(abi_file)


from dao_summon_helpers import assemble_meme_summoner_args, calculate_dao_address



from constants_utils import (
    BASENAMES_REGISTRAR_CONTROLLER_ADDRESS_MAINNET,
    BASENAMES_REGISTRAR_CONTROLLER_ADDRESS_TESTNET,
    L2_RESOLVER_ADDRESS_MAINNET,
    L2_RESOLVER_ADDRESS_TESTNET,
    SUMMON_CONTRACTS,
    DEFAULT_CHAIN_ID,
)


from dotenv import dotenv_values

config = dotenv_values(".env")

# Get configuration from environment variables
API_KEY_NAME = os.getenv("CDP_API_KEY_NAME")
PRIVATE_KEY = os.getenv("CDP_PRIVATE_KEY", "").replace('\\n', '\n')

# Configure CDP with environment variables
Cdp.configure(API_KEY_NAME, PRIVATE_KEY)

# Create a new wallet on the Base Sepolia testnet
# You could make this a function for the agent to create a wallet on any network
# If you want to use Base Mainnet, change Wallet.create() to Wallet.create(network_id="base-mainnet")
# see https://docs.cdp.coinbase.com/mpc-wallet/docs/wallets for more information
# agent_wallet = Wallet.create(network_id="base-mainnet")

# NOTE: the wallet is not currently persisted, meaning that it will be deleted after the agent is stopped. To persist the wallet, see https://docs.cdp.coinbase.com/mpc-wallet/docs/wallets#developer-managed-wallets
# Here's an example of how to persist the wallet:
# WARNING: This is for development only - implement secure storage in production!

# Export wallet data (contains seed and wallet ID)
# wallet_data = agent_wallet.export_data()
# wallet_dict = wallet_data.to_dict()

# Example of saving to encrypted local file
# file_path = "base_wallet_seed.json"
# agent_wallet.save_seed(file_path, encrypt=True)
# print(f"Seed for wallet {agent_wallet.id} saved to {file_path}")

# Example of loading a saved wallet:
# 1. Fetch the wallet by ID
# agent_wallet = Wallet.fetch("278ecde2-f10c-42db-9fda-fb4db022fcca") # testnet
agent_wallet = Wallet.fetch("6dafdeee-a356-408f-9d27-e55abbb1ea64") # mainnet
# 2. Load the saved seed
agent_wallet.load_seed("base_wallet_seed.json")

# Example of importing previously exported wallet data:
# imported_wallet = Wallet.import_data(wallet_dict)

# Request funds from the faucet (only works on testnet)
# faucet = agent_wallet.faucet()
# print(f"Faucet transaction: {faucet}")
# print(f"Agent wallet address: {agent_wallet.default_address.address_id}")


# Function to get the balance of a specific asset
def get_balance(asset_id):
    """
    Get the balance of a specific asset in the agent's wallet.
    
    Args:
        asset_id (str): Asset identifier ("eth", "usdc") or contract address of an ERC-20 token
    
    Returns:
        str: A message showing the current balance of the specified asset
    """
    balance = agent_wallet.balance(asset_id)
    return f"Current balance of {asset_id}: {balance}"

# Function to get the address of the current agent
def get_agent_address():
    """
    Get the address of the current agent's wallet.

    Returns:
        str: The address of the agent
    """
    address = agent_wallet.default_address.address_id
    return f"Current address: {address}"

# Function to request ETH from the faucet (testnet only)
def request_eth_from_faucet():
    """
    Request ETH from the Base Sepolia testnet faucet.
    
    Returns:
        str: Status message about the faucet request
    """
    if agent_wallet.network_id == "base-mainnet":
        return "Error: The faucet is only available on Base Sepolia testnet."

    faucet_tx = agent_wallet.faucet()
    return f"Requested ETH from faucet. Transaction: {faucet_tx}"


# Function to generate art using DALL-E (requires separate OpenAI API key)
def generate_art(prompt):
    """
    Generate art using DALL-E based on a text prompt.
    
    Args:
        prompt (str): Text description of the desired artwork
    
    Returns:
        str: Status message about the art generation, including the image URL if successful
    """
    try:
        client = OpenAI()
        response = client.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size="1024x1024",
            quality="standard",
            n=1,
        )

        image_url = response.data[0].url
        return f"Generated artwork available at: {image_url}"

    except Exception as e:
        return f"Error generating artwork: {str(e)}"

# functions to interact with daos
def vote_on_dao_proposal(proposal_id: str, vote: bool) -> str:
    """
    Summon a DAO.

    Args:
        proposal_id (int): The proposal ID.
        vote (bool): The vote.

    Returns:
        str: Success or error message.
    """
    dao_address = os.getenv("TARGET_DAO")
    if not isinstance(dao_address, str) or not isinstance(proposal_id, str) or not isinstance(vote, bool):
        return "Invalid input types"

    try:

        args_dict = {
            "id": proposal_id,
            "approved": vote,
        }

        invocation = agent_wallet.invoke_contract(
            contract_address=dao_address,
            method="submitVote",
            args=args_dict,
            abi=baal_abi,
            # amount=amount,
            # asset_id="eth",
        )
        invocation.wait()
        return f"Successfully voted on proposal id {proposal_id} for dao address {dao_address}"


    except Exception as e:
        return f"Error Voting in DAO: {str(e)}"
    
def summon_dao(dao_name, token_symbol, image, description, agent_wallet_address):
    """
    Summon a DAO.

    Args:
        dao_name (str): Name of the DAO.
        token_symbol (str): Token symbol for the DAO.
        image (str): Image URL for the dao avatar
        description (str): Description of the DAO.
        agent_wallet_address (str): Address of the agent wallet.

    Returns:
        str: Success or error message.
    """
    try:
        # Assemble arguments for summoning the DAO
        summon_args = assemble_meme_summoner_args(dao_name, token_symbol, image, description, agent_wallet_address, DEFAULT_CHAIN_ID)


        initialization_loot_token_params = summon_args[0]
        initialization_share_token_params = summon_args[1]
        initialization_shaman_params = summon_args[2]
        post_initialization_actions = summon_args[3]
        salt_nonce = int(summon_args[4])

        summon_args_dict = {
            "initializationLootTokenParams": Web3.to_hex(initialization_loot_token_params),
            "initializationShareTokenParams": Web3.to_hex(initialization_share_token_params),
            "initializationShamanParams": Web3.to_hex(initialization_shaman_params),
            "postInitializationActions": post_initialization_actions,
            "saltNonce": str(salt_nonce),
        }

        print("Summoning DAO with...", SUMMON_CONTRACTS['YEET24_SUMMONER'][DEFAULT_CHAIN_ID])

        # Invoke the contract
        summon_invocation = agent_wallet.invoke_contract(
            contract_address=SUMMON_CONTRACTS['YEET24_SUMMONER'][DEFAULT_CHAIN_ID],
            method="summonBaalFromReferrer",
            args=summon_args_dict,
            abi=yeet24_hos_summoner_abi,
            amount=None,
            asset_id="eth",
        )
        summon_invocation.wait()

        return f"Successfully summoned DAO {calculate_dao_address(salt_nonce)}"

    except Exception as e:
        return f"Error summoning DAO: {str(e)}"


# function to submit a proposal
def submit_dao_proposal(proposal_title: str, proposal_description: str, proposal_link: str) -> str:
    """
    Submit a DAO Proposal. 
    Proposals can be accessed at this link https://admin.daohaus.club/#/molochv3/0x2105/0x5dc22d379d052ba0c6210101450a943e48c5404b/proposals

    Args:
        proposal_title (str): The proposal title.
        proposal_description (str): The proposal description.
        proposal_link (str): The proposal link.

    Returns:
        str: Success or error message.
    """
    dao_address = os.getenv("TARGET_DAO")

    if not isinstance(dao_address, str) or not isinstance(proposal_title, str):
        return "Invalid input types"
    
    proposal_details = {
    "title": proposal_title,
    "description": proposal_description,
    "contentURI": proposal_link,
    "contentURIType": {"type": "static", "value": "url"},
    "proposalType": {"type": "static", "value": "Signal"},  
    }

    proposal = json.dumps(proposal_details)


    try:

        args_dict = {
            "proposalData": "",
            "expiration": "0",
            "baalGas": "0",
            "details": proposal
        }

        invocation = agent_wallet.invoke_contract(
            contract_address=dao_address,
            method="submitProposal",
            args=args_dict,
            abi=baal_abi,
            # amount=amount,
            # asset_id="eth",
        )
        invocation.wait()
        
        return f"Successfully submitted proposal for dao address {dao_address}. Proposal details link: https://admin.daohaus.club/#/molochv3/0x2105/0x5dc22d379d052ba0c6210101450a943e48c5404b/proposals"


    except Exception as e:
        return f"Error Submitting Proposal in DAO: {str(e)}"
    
def get_dao_proposals():
    """
    Get all DAO proposals.

    this returns the first 10 proposals using subgrounds
            result = self.sg.query([
                proposals.proposalId,
                proposals.yesVotes,
                proposals.noVotes,
                proposals.yesBalance,
                proposals.noBalance,
                proposals.createdAt,
                proposals.details,
                proposals.votes,
                proposals.age,  # Use synthetic field as a regular field
            ])

        age is the last index in seconds 
    
    """

    try:
        # Construct the query
        proposals = dh_graph.get_proposals_data()
        return proposals
    except Exception as e:
        return f"Error getting DAO proposals: {str(e)}"

def get_dao_proposal(proposal_id: int) -> str:
    """
    Get a specific DAO proposal.

    Args:
        proposal_id (str): The proposal ID.

    Returns:
        str: The proposal details.
    """
    try:
        # Construct the query
        proposal = dh_graph.get_proposal_data(proposal_id)
        return proposal
    except Exception as e:
        return f"Error getting DAO proposal: {str(e)}"
    
def get_proposal_count() -> str:
    """
    Get the current proposal count

    Returns:
        str: the count
    """
    try:
        # Construct the query
        proposals = dh_graph.get_proposal_count()
        return proposals
    except Exception as e:
        return f"Error getting proposals count: {str(e)}"

# function to cast to farcaster
def cast_to_farcaster(content: str):
    """
    Cast a message to Warpcast.

    Args:
        content (str): The content to cast

    Returns:
        str: Status message about the cast
    """
    return farcaster_bot.post_cast(content)

def check_cast_replies():
    """
    Check recent farcaster replies.

    Returns:
        str: Formatted string of recent replies by user
    """
    replies = farcaster_bot.get_replies()
    if not replies:
        return "No recent mentions found"

    return replies

def check_cast_notifications():
    # TODO: errors with 500
    """
    Check recent farcaster notifications.

    wrapcast url will be in this format: (https://warpcast.com/<author>/<hash>) 

    Returns:
        str: Formatted string of recent notifications
    """
    response = farcaster_bot.get_notifications()

    return response

def mark_notifications_as_seen():

    """
    Mark notifications as seen.

    Returns:
        str: Status message about the cast
    """
    response = farcaster_bot.mark_notifications_as_seen()
    return response

def cast_reply(content: str, parentHash: str, parent_fid: int):
    """
    Cast a message to Warpcast as a reply to another cast.
    uses parentHash to reply and parent author fid

    Args:
        content (str): The content to cast
        parentHash (str): The parent cast hash (for reply)

    Returns:
        str: Status message about the cast
    """
    response = farcaster_bot.post_cast(content, parent=parentHash, parent_fid=parent_fid)
    return response

def check_recent_agent_casts():
    """
    Get recent casts from the agent.

    Returns:
        str: Formatted string of recent casts
    """
    response = farcaster_bot.get_casts()
    return response

def check_recent_user_casts(fid: str):
    """
    Get recent casts from the agent.

    Returns:
        str: Formatted string of recent casts
    """
    response = farcaster_bot.get_casts(fid)
    return response

def check_user_profile(fid: str):
    """
    Get user profile.

    Returns:
        str: Formatted string of user profile (exclude @ sign)
    """
    response = farcaster_bot.get_user_by_username(fid)
    return response

# Create the Based Agent with all available functions
based_agent = Agent(
    name="Based Agent",
    instructions=instructions,
    functions=[
        get_balance,
        get_agent_address,
        generate_art,  # Uncomment this line if you have configured the OpenAI API
        cast_to_farcaster,
        check_cast_replies,
        check_cast_notifications,
        # mark_notifications_as_seen,
        cast_reply,
        check_recent_agent_casts,
        check_recent_user_casts,
        check_user_profile,
        submit_dao_proposal,
        vote_on_dao_proposal,
        # get_current_proposal_count
        get_dao_proposals,
        get_dao_proposal,
        get_proposal_count,
        summon_dao
    ],
)

# add the following import to the top of the file, add the code below it, and add the new functions to the based_agent.functions list

# from farcaster_utils import FarcasterBot

# # Initialize FarcvasterBot with your credentials
farcaster_bot = FarcasterBot()
dh_graph = DaohausGraphData()
    

# To add a new function:
# 1. Define your function above (follow the existing pattern)
# 2. Add appropriate error handling
# 3. Add the function to the based_agent's functions list
# 4. If your function requires new imports or global variables, add them at the top of the file
# 5. Test your new function thoroughly before deploying

# Example of adding a new function:
# def my_new_function(param1, param2):
#     """
#     Description of what this function does.
#
#     Args:
#         param1 (type): Description of param1
#         param2 (type): Description of param2
#
#     Returns:
#         type: Description of what is returned
#     """
#     try:
#         # Your function logic here
#         result = do_something(param1, param2)
#         return f"Operation successful: {result}"
#     except Exception as e:
#         return f"Error in my_new_function: {str(e)}"

# Then add to based_agent.functions:
# based_agent = Agent(
#     ...
#     functions=[
#         ...
#         my_new_function,
#     ],
# )