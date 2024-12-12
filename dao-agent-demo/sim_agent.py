class SimAgent:
    def __init__(self, instructions):
        self.instructions = instructions
        self.key = instructions["Key"]
        self.name = instructions["Name"]
        self.type = instructions["Type"]
        self.address = None
        self.agent = None

        

    def set_address(self, address):
        self.address = address
    
    def set_agent(self, agent):
        self.agent = agent

    def get_instructions_string(self):
        return ", ".join(f"{key}: {value}" for key, value in self.instructions.items())


    def get_sim_instructions_from_json(self):
        if self.instructions["Type"] == "GM":
            return f"""
            Name: {self.instructions["Name"]}
            Identity: {self.instructions["Identity"]}
            Functionality: {self.instructions["Functionality"]}
            ScenarioBuildingRules: {self.instructions["ScenarioBuildingRules"]}
            NarrativeFocus: {self.instructions["NarrativeFocus"]}
            Platform: {self.instructions["Platform"]}
            Extra: {self.instructions["Extra"]}
            GovernanceStructure: "The governance structure is a DAO. 1 player has initiative to make a proposal each round. there are several phases of each round: "
            "gm introduces a scenario, players deliberate and negotiate, the player with initiative makes a proposal, all players vote on the proposal,"
            "the gm resolves the proposal and checks if the proposal actions were a success with a d20."
            """
        else:
            return f"""
            Name: {self.instructions["Name"]}
            Identity: {self.instructions["Identity"]}
            Functionality: You have the ability to submit a proposal on chain and to generate art. But only do this if specifically prompted to do so.
            Platform: {self.instructions["Platform"]}
            """

    def __repr__(self):
        return f"Agent(key={self.key}, name={self.name})"